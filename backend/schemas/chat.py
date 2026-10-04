from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from backend.schemas.common import Disclaimer, LanguageCode, ORMModel, clean


class ChatRequest(BaseModel):
    message: clean(2000)
    language: LanguageCode | None = None


class Source(BaseModel):
    ref: int
    title: str
    source: str
    url: str
    page: int | None = None
    score: float


class ChatResponse(Disclaimer):
    chat_id: uuid.UUID
    response: str
    language: str
    sources: list[Source]
    grounded: bool
    blocked: bool
    llm_used: bool


class ChatHistoryItem(ORMModel):
    id: uuid.UUID
    message: str
    response: str
    channel: str
    language: str
    sources: list
    created_at: datetime


class VoiceChatResponse(Disclaimer):
    chat_id: uuid.UUID
    transcript: str
    detected_language: str
    response: str
    sources: list[Source]
    blocked: bool
    audio_base64: str | None = None
    audio_format: str | None = None
    tts_available: bool
    tts_note: str | None = None
