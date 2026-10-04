"""Thin, synchronous client for the local Ollama runtime (no paid APIs)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from backend.config import settings
from backend.utils.logging import get_logger
from backend.utils.metrics import track_llm

log = get_logger(__name__)


class LLMUnavailable(Exception):
    """Raised when Ollama is down, the model is not pulled, or the call fails."""


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=httpx.Timeout(timeout or settings.OLLAMA_TIMEOUT_SECONDS, connect=5.0)
        )
        self._models_cache: tuple[float, set[str]] = (0.0, set())

    # ---- discovery -------------------------------------------------------------------
    def list_models(self, max_age: float = 30.0) -> set[str]:
        ts, models = self._models_cache
        if time.monotonic() - ts < max_age:
            return models
        try:
            resp = self._client.get("/api/tags", timeout=5.0)
            resp.raise_for_status()
            models = {m["name"] for m in resp.json().get("models", [])}
        except Exception as exc:
            log.debug("ollama list_models failed: %s", exc)
            models = set()
        self._models_cache = (time.monotonic(), models)
        return models

    def has_model(self, model: str) -> bool:
        models = self.list_models()
        if model in models:
            return True
        # "nomic-embed-text" is stored as "nomic-embed-text:latest".
        return ":" not in model and f"{model}:latest" in models

    # ---- generation ------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> str:
        model = model or settings.OLLAMA_PRIMARY_MODEL
        if not settings.LLM_ENABLED:
            raise LLMUnavailable("LLM disabled by configuration")
        if not self.has_model(model):
            raise LLMUnavailable(f"Model {model} is not available in Ollama (still pulling?)")
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": settings.OLLAMA_NUM_CTX},
        }
        if json_mode:
            body["format"] = "json"
        try:
            with track_llm(model, "chat"):
                resp = self._client.post("/api/chat", json=body)
                resp.raise_for_status()
                return resp.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailable(f"Ollama chat failed: {exc}") from exc

    def chat_json(self, messages: list[dict[str, str]], model: str | None = None, **kw: Any) -> dict[str, Any]:
        raw = self.chat(messages, model=model, json_mode=True, **kw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end <= start:
                raise LLMUnavailable("LLM returned non-JSON output") from None
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMUnavailable("LLM returned malformed JSON") from exc
        if not isinstance(data, dict):
            raise LLMUnavailable("LLM JSON output was not an object")
        return data

    # ---- embeddings ------------------------------------------------------------------
    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model = model or settings.OLLAMA_EMBED_MODEL
        if not self.has_model(model):
            raise LLMUnavailable(f"Embedding model {model} is not available in Ollama")
        try:
            with track_llm(model, "embed"):
                resp = self._client.post("/api/embed", json={"model": model, "input": texts})
                if resp.status_code == 404:  # older Ollama: one prompt per call
                    return [self._embed_legacy(t, model) for t in texts]
                resp.raise_for_status()
                return resp.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailable(f"Ollama embed failed: {exc}") from exc

    def _embed_legacy(self, text: str, model: str) -> list[float]:
        resp = self._client.post("/api/embeddings", json={"model": model, "prompt": text})
        resp.raise_for_status()
        return resp.json()["embedding"]

    def ping(self) -> bool:
        try:
            return self._client.get("/api/version", timeout=3.0).status_code == 200
        except httpx.HTTPError:
            return False


def model_for(language: str | None, default: str | None = None) -> str:
    """Per-language override (OLLAMA_LANGUAGE_MODELS), else the given default / primary model."""
    return settings.OLLAMA_LANGUAGE_MODELS.get(language or "", default or settings.OLLAMA_PRIMARY_MODEL)


_client: OllamaClient | None = None


def get_ollama() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
