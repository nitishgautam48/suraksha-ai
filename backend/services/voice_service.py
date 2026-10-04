"""Module 5: Voice assistant - Audio -> Whisper -> Ollama (RAG) -> Coqui TTS."""

from __future__ import annotations

import base64

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend import i18n
from backend.models import User
from backend.security.file_validation import ValidatedFile
from backend.services.chat_service import chat
from backend.voice import stt, tts

SUPPORTED_LANGS = set(i18n.CODES)


def voice_chat(db: Session, user: User, audio: ValidatedFile, language: str | None, want_audio: bool) -> dict:
    try:
        transcript = stt.transcribe(audio.data, suffix=audio.ext, language=language)
    except stt.STTUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if not transcript.text:
        raise HTTPException(422, "No speech detected in the audio")

    lang = transcript.language if transcript.language in SUPPORTED_LANGS else (language or user.language or "en")
    answer = chat(db, user, transcript.text[:2000], lang, channel="voice")

    audio_b64, note = None, None
    tts_ok = lang in tts.tts_languages()
    if want_audio:
        try:
            audio_b64 = base64.b64encode(tts.synthesize(answer.text, lang)).decode("ascii")
        except tts.TTSUnavailable as exc:
            tts_ok, note = False, str(exc)
    return {
        "chat_id": answer.history_id,
        "transcript": transcript.text,
        "detected_language": lang,
        "response": answer.text,
        "sources": answer.sources,
        "blocked": answer.blocked,
        "audio_base64": audio_b64,
        "audio_format": "wav" if audio_b64 else None,
        "tts_available": tts_ok and audio_b64 is not None,
        "tts_note": note,
    }
