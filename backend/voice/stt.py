"""Speech-to-text with OpenAI Whisper running locally (open-source weights, no API)."""

from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass

from backend.config import settings
from backend.i18n import LANGUAGES
from backend.utils.logging import get_logger

log = get_logger(__name__)

SUPPORTED = {code for code, lang in LANGUAGES.items() if lang.whisper}  # Odia: auto-detect


class STTUnavailable(Exception):
    pass


@dataclass
class Transcript:
    text: str
    language: str


_model = None
_lock = threading.Lock()


def _load():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                if not settings.VOICE_ENABLED:
                    raise STTUnavailable("Voice features are disabled")
                try:
                    import whisper
                except ImportError as exc:
                    raise STTUnavailable("openai-whisper is not installed (build with INSTALL_VOICE=true)") from exc
                log.info("Loading Whisper model %s", settings.WHISPER_MODEL)
                _model = whisper.load_model(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
    return _model


def transcribe(audio: bytes, suffix: str = ".wav", language: str | None = None) -> Transcript:
    model = _load()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)
        path = tmp.name
    try:
        opts = {"fp16": False, "task": "transcribe"}
        if language in SUPPORTED:
            opts["language"] = language
        with _lock:  # Whisper models are not thread-safe
            result = model.transcribe(path, **opts)
    except Exception as exc:
        raise STTUnavailable(f"Transcription failed: {exc}") from exc
    finally:
        os.unlink(path)
    detected = result.get("language") or language or "en"
    return Transcript(text=(result.get("text") or "").strip(), language=detected)
