"""RAG-grounded assistant: Question -> retrieve context -> Ollama -> guardrails -> history."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import i18n
from backend.ai import prompts
from backend.ai.guardrails import is_advice_request, refusal, sanitize_llm_output
from backend.ai.ollama_client import LLMUnavailable, get_ollama, model_for
from backend.models import ChatHistory, User
from backend.rag.retriever import RetrievedChunk, format_context, retrieve, sources_payload
from backend.services import preferences
from backend.services.activity_service import record_activity
from backend.services.gamification_service import award
from backend.utils.logging import get_logger
from backend.utils.metrics import GUARDRAIL_BLOCKS
from backend.utils.redact import redact

log = get_logger(__name__)


@dataclass
class ChatAnswer:
    text: str
    sources: list[dict] = field(default_factory=list)
    grounded: bool = False
    blocked: bool = False
    llm_used: bool = False
    history_id: object = None


def _history_messages(db: Session, user_id, turns: int = 3) -> list[dict[str, str]]:
    rows = db.scalars(
        select(ChatHistory).where(ChatHistory.user_id == user_id).order_by(ChatHistory.created_at.desc()).limit(turns)
    ).all()
    msgs: list[dict[str, str]] = []
    for r in reversed(rows):
        msgs += [{"role": "user", "content": r.message[:800]}, {"role": "assistant", "content": r.response[:800]}]
    return msgs


def _offline_answer(chunks: list[RetrievedChunk], language: str) -> str:
    if chunks and language == "en":
        snippet = re.sub(r"\s+", " ", chunks[0].text)[:600]
        return f"From our safety library ({chunks[0].title}): {snippet} [1]"
    return i18n.t("chat_fallback", language)


def generate_answer(db: Session, user: User, question: str, language: str, voice: bool = False) -> ChatAnswer:
    if is_advice_request(question):
        GUARDRAIL_BLOCKS.labels("input").inc()
        return ChatAnswer(text=refusal(language), blocked=True)

    chunks = retrieve(question)
    system = prompts.ASSISTANT_SYSTEM.format(language=prompts.LANGUAGE_NAMES.get(language, "English"))
    if voice:
        system += prompts.VOICE_STYLE
    if preferences.is_elder(user):
        system += prompts.ELDER_STYLE
    messages = [
        {"role": "system", "content": system},
        *_history_messages(db, user.id),
        {"role": "user", "content": prompts.ASSISTANT_USER.format(context=format_context(chunks), question=question)},
    ]
    try:
        text = get_ollama().chat(messages, model=model_for(language), temperature=0.3, max_tokens=500).strip()
        llm_used = True
    except LLMUnavailable as exc:
        log.info("Chat falling back to offline answer: %s", exc)
        text, llm_used = _offline_answer(chunks, language), False
    text, blocked = sanitize_llm_output(text, language)
    if blocked:
        GUARDRAIL_BLOCKS.labels("output").inc()
    if voice:
        text = re.sub(r"\[\d+\]|[*#`_]", "", text).strip()
    return ChatAnswer(text=text, sources=sources_payload(chunks), grounded=bool(chunks), blocked=blocked, llm_used=llm_used)


def chat(db: Session, user: User, message: str, language: str, channel: str = "text") -> ChatAnswer:
    message, _ = redact(message)  # never send or store OTPs, card or account numbers
    answer = generate_answer(db, user, message, language, voice=channel == "voice")
    row = ChatHistory(
        user_id=user.id, message=message, response=answer.text, channel=channel, language=language, sources=answer.sources
    )
    db.add(row)
    record_activity(db, user.id, "chat")
    award(db, user.id, "chat")
    db.commit()
    answer.history_id = row.id
    return answer
