"""Module 5: Voice assistant."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.api.deps import DB, ConsentedUser
from backend.config import settings
from backend.schemas.chat import VoiceChatResponse
from backend.schemas.common import LanguageCode
from backend.security.file_validation import read_and_validate
from backend.security.rate_limit import limiter
from backend.services.voice_service import voice_chat

router = APIRouter(prefix="/voice", tags=["Voice Assistant"])


@router.post("/chat", response_model=VoiceChatResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
async def voice(
    request: Request,
    user: ConsentedUser,
    db: DB,
    audio: Annotated[UploadFile, File(description="Recorded question (wav, mp3, m4a, ogg, webm, flac)")],
    language: Annotated[LanguageCode | None, Form(description="Hint: en, hi, gu, mr. Omit to auto-detect.")] = None,
    tts: Annotated[bool, Form(description="Return a spoken reply (Hindi/English)")] = True,
):
    """Audio -> Whisper speech-to-text -> RAG-grounded Ollama answer -> Coqui TTS audio (base64 WAV)."""
    vf = await read_and_validate(audio, "audio")
    return await run_in_threadpool(voice_chat, db, user, vf, language, tts)


@router.post("/command")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def command(
    request: Request,
    user: ConsentedUser,
    text: Annotated[str | None, Form(max_length=300, description="Phrase from the browser's speech recognition")] = None,
    audio: Annotated[UploadFile | None, File(description="Or a short recording, transcribed by Whisper")] = None,
    language: Annotated[LanguageCode | None, Form()] = None,
):
    """Voice navigation: returns the app command for a spoken phrase in any of the 12 languages
    (scan, help, report, read, stop, learn, family, alerts, settings, habits, chat, home, back).
    Nothing is stored."""
    from backend.utils.redact import redact
    from backend.voice import stt
    from backend.voice.commands import parse_command

    if text is None and audio is None:
        raise HTTPException(422, "Send 'text' or 'audio'")
    if text is None:
        vf = await read_and_validate(audio, "audio")
        try:
            t = await run_in_threadpool(stt.transcribe, vf.data, vf.ext, language or user.language)
        except stt.STTUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        text = t.text
    return {"intent": parse_command(text), "transcript": redact(text or "")[0]}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    language: LanguageCode = "en"


@router.get("/tts")
def speak_status(user: ConsentedUser):
    """Whether the server can read text aloud, and in which languages (no model is loaded)."""
    from backend.voice import tts

    ok = tts.available()
    return {"available": ok, "languages": sorted(tts.tts_languages()) if ok else []}


@router.post(
    "/tts",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}, "description": "Spoken text (WAV)"}},
)
@limiter.limit(settings.RATE_LIMIT_AI)
async def speak(request: Request, data: SpeakRequest, user: ConsentedUser):
    """Read text aloud with the server's Coqui voice (English and Hindi built in). The web app uses this
    when the device has no voice for the language, e.g. Windows without a Hindi voice installed."""
    from backend.voice import tts

    if data.language not in tts.tts_languages():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No server voice for '{data.language}'")
    try:
        wav = await run_in_threadpool(tts.synthesize, data.text, data.language)
    except tts.TTSUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})
