from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from backend.api.deps import DB, ConsentedUser, user_language
from backend.config import settings
from backend.models import ChatHistory
from backend.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse
from backend.security.rate_limit import limiter
from backend.services.chat_service import chat

router = APIRouter(tags=["AI Safety Assistant"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
def chat_endpoint(request: Request, data: ChatRequest, user: ConsentedUser, db: DB):
    """Ask the RAG-grounded safety assistant. Investment-advice questions are politely declined."""
    lang = user_language(user, data.language)
    answer = chat(db, user, data.message, lang)
    return {
        "chat_id": answer.history_id,
        "response": answer.text,
        "language": lang,
        "sources": answer.sources,
        "grounded": answer.grounded,
        "blocked": answer.blocked,
        "llm_used": answer.llm_used,
    }


@router.get("/chat/history", response_model=list[ChatHistoryItem])
def chat_history(user: ConsentedUser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return db.scalars(
        select(ChatHistory)
        .where(ChatHistory.user_id == user.id)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
