"""Text-to-speech with Coqui TTS (local, open-source).

English uses a light VITS voice. Hindi uses the multilingual XTTS-v2 model (requires accepting the
Coqui Public Model License via COQUI_TOS_AGREED=1). Gujarati and Marathi have no Coqui voice, so
voice replies in those languages are returned as text only.
"""

from __future__ import annotations

import io
import threading

from backend.config import settings
from backend.utils.logging import get_logger

log = get_logger(__name__)


class TTSUnavailable(Exception):
    pass


_models: dict[str, object] = {}
_lock = threading.Lock()


def tts_languages() -> set[str]:
    """English (VITS) and Hindi (XTTS-v2) are built in; others need TTS_CUSTOM_MODELS."""
    return {"en", "hi"} | set(settings.TTS_CUSTOM_MODELS)


TTS_LANGS = tts_languages()


def available() -> bool:
    """Cheap check (no model load): enabled in settings and the coqui-tts package is installed."""
    import importlib.util

    return bool(settings.VOICE_ENABLED and settings.TTS_ENABLED and importlib.util.find_spec("TTS"))


def _load(name: str, custom: dict[str, str] | None):
    try:
        from TTS.api import TTS
    except ImportError as exc:
        raise TTSUnavailable("coqui-tts is not installed (build with INSTALL_VOICE=true)") from exc
    log.info("Loading Coqui TTS model %s", name)
    try:
        if custom:
            kwargs = {k: custom[k] for k in ("model_path", "config_path", "vocoder_path", "vocoder_config_path") if k in custom}
            return TTS(progress_bar=False, **kwargs).to("cpu")
        return TTS(name, progress_bar=False).to("cpu")
    except Exception as exc:
        raise TTSUnavailable(f"Could not load TTS model {name}: {exc}") from exc


def _get(language: str):
    if not (settings.VOICE_ENABLED and settings.TTS_ENABLED):
        raise TTSUnavailable("Text-to-speech is disabled")
    if language not in tts_languages():
        raise TTSUnavailable(f"No server voice for language '{language}' - use the device's speech synthesis")
    custom = settings.TTS_CUSTOM_MODELS.get(language)
    name = f"custom:{language}" if custom else settings.TTS_MODEL_EN if language == "en" else settings.TTS_MODEL_MULTILINGUAL
    with _lock:
        if name not in _models:
            _models[name] = _load(name, custom)
        return _models[name], name


def synthesize(text: str, language: str) -> bytes:
    """Return WAV bytes."""
    import numpy as np
    import soundfile as sf

    tts, name = _get(language)
    kwargs = {}
    if name.startswith("custom:"):
        speaker = settings.TTS_CUSTOM_MODELS[language].get("speaker")
        kwargs = {"speaker": speaker} if speaker else {}
    elif "xtts" in name or "multilingual" in name:
        kwargs = {"language": language, "speaker": settings.TTS_HINDI_SPEAKER}
    with _lock:
        try:
            wav = tts.tts(text=text[:1200], **kwargs)
        except Exception as exc:
            raise TTSUnavailable(f"Speech synthesis failed: {exc}") from exc
    rate = getattr(getattr(tts, "synthesizer", None), "output_sample_rate", 22050) or 22050
    buf = io.BytesIO()
    sf.write(buf, np.asarray(wav, dtype=np.float32), rate, format="WAV")
    return buf.getvalue()
