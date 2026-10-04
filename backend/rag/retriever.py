"""Question -> retrieve context -> grounded prompt context."""

from __future__ import annotations

from dataclasses import dataclass

from backend.ai.ollama_client import LLMUnavailable, get_ollama
from backend.config import settings
from backend.rag import store
from backend.utils.logging import get_logger
from backend.utils.metrics import RAG_RETRIEVALS

log = get_logger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    title: str
    source: str
    url: str
    score: float
    page: int | None = None


def retrieve(question: str, k: int | None = None, min_score: float | None = None) -> list[RetrievedChunk]:
    k = k or settings.RAG_TOP_K
    min_score = settings.RAG_MIN_RELEVANCE if min_score is None else min_score
    try:
        vec = get_ollama().embed([f"search_query: {question}"])[0]
        hits = store.query(vec, k)
    except (LLMUnavailable, store.VectorStoreUnavailable) as exc:
        log.info("RAG retrieval unavailable: %s", exc)
        RAG_RETRIEVALS.labels("error").inc()
        return []
    except Exception as exc:  # pragma: no cover - unexpected chroma errors
        log.warning("RAG retrieval failed: %s", exc)
        store.reset_collection_cache()
        RAG_RETRIEVALS.labels("error").inc()
        return []
    chunks = [
        RetrievedChunk(
            text=h["text"],
            title=h["metadata"].get("title", ""),
            source=h["metadata"].get("source", ""),
            url=h["metadata"].get("url", ""),
            score=h["score"],
            page=h["metadata"].get("page") or None,
        )
        for h in hits
        if h["score"] >= min_score
    ]
    RAG_RETRIEVALS.labels("hit" if chunks else "empty").inc()
    return chunks


def format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no matching passages found in the knowledge base)"
    return "\n\n".join(
        f"[{i}] {c.title} ({c.source}{f', page {c.page}' if c.page else ''})\n{c.text}" for i, c in enumerate(chunks, 1)
    )


def sources_payload(chunks: list[RetrievedChunk]) -> list[dict]:
    out = []
    for i, c in enumerate(chunks, 1):
        out.append({"ref": i, "title": c.title, "source": c.source, "url": c.url, "page": c.page, "score": c.score})
    return out
