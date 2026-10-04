"""Admin-only endpoints (RBAC)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.deps import DB, require_permission
from backend.models import AuditLog, User
from backend.schemas.analysis import FeedbackAdminOut
from backend.schemas.auth import RoleUpdate, UserOut
from backend.schemas.common import Message
from backend.security.file_validation import read_knowledge_upload
from backend.security.sanitize import strip_html
from backend.services import feedback_service, knowledge_service
from backend.services.audit_service import record_audit

KnowledgeTopic = Literal["scam_detection", "upi_frauds", "cyber_safety", "financial_literacy", "general"]

router = APIRouter(prefix="/admin", tags=["Admin"])


class AuditOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    method: str | None
    path: str | None
    status_code: int | None
    ip_address: str | None
    request_id: str | None
    details: dict
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/users", response_model=list[UserOut])
def users(
    db: DB,
    _: User = Depends(require_permission("users:read")),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return db.scalars(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)).all()


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: uuid.UUID, data: RoleUpdate, db: DB, admin: User = Depends(require_permission("users:write"))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    old = user.role
    user.role = data.role
    db.commit()
    record_audit("admin.role_change", admin.id, details={"target": str(user_id), "from": old, "to": data.role})
    return user


@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_active(user_id: uuid.UUID, active: bool, db: DB, admin: User = Depends(require_permission("users:write"))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_active = active
    db.commit()
    record_audit("admin.user_active", admin.id, details={"target": str(user_id), "active": active})
    return user


@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(
    db: DB,
    _: User = Depends(require_permission("audit:read")),
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    return db.scalars(q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()


@router.post("/knowledge/ingest", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def ingest(_: User = Depends(require_permission("knowledge:ingest"))):
    """Re-index every knowledge document (bundled, uploaded and fetched) into ChromaDB on the worker."""
    from backend.workers.tasks import ingest_knowledge

    task = ingest_knowledge.delay()
    return {"detail": f"Ingestion queued (task {task.id})"}


class KnowledgeDocOut(BaseModel):
    id: uuid.UUID
    doc_key: str
    title: str
    source: str
    url: str | None
    topic: str
    origin: str
    file_type: str
    status: str
    chunks: int
    pages: int | None
    error: str | None
    created_at: datetime
    ingested_at: datetime | None

    model_config = {"from_attributes": True}


class FetchRequest(BaseModel):
    url: str = Field(pattern=r"^https://", max_length=1000)
    title: str = Field(min_length=3, max_length=300)
    source: str = Field(min_length=2, max_length=200)
    topic: KnowledgeTopic = "general"


@router.get("/knowledge/documents", response_model=list[KnowledgeDocOut])
def knowledge_documents(db: DB, _: User = Depends(require_permission("knowledge:ingest"))):
    return knowledge_service.list_documents(db)


@router.post("/knowledge/documents", response_model=KnowledgeDocOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_knowledge(
    db: DB,
    file: Annotated[UploadFile, File(description="Official PDF, Markdown, text or HTML document")],
    title: Annotated[str, Form(min_length=3, max_length=300)],
    source: Annotated[str, Form(min_length=2, max_length=200, description="Publisher, e.g. 'Reserve Bank of India'")],
    url: Annotated[str | None, Form(max_length=1000)] = None,
    topic: Annotated[KnowledgeTopic, Form()] = "general",
    admin: User = Depends(require_permission("knowledge:ingest")),
):
    """Add a document to the knowledge base. It is chunked, embedded and indexed on the worker."""
    data, _, ext = await read_knowledge_upload(file)
    doc = knowledge_service.add_upload(db, data, ext, strip_html(title), strip_html(source), url, topic, admin.id)
    record_audit("admin.knowledge_upload", admin.id, details={"doc": doc.doc_key, "title": doc.title})
    return doc


@router.post("/knowledge/documents/{doc_id}/reingest", response_model=KnowledgeDocOut, status_code=status.HTTP_202_ACCEPTED)
def reingest_knowledge(doc_id: uuid.UUID, db: DB, _: User = Depends(require_permission("knowledge:ingest"))):
    return knowledge_service.reingest(db, doc_id)


@router.delete("/knowledge/documents/{doc_id}", response_model=Message)
def delete_knowledge(doc_id: uuid.UUID, db: DB, admin: User = Depends(require_permission("knowledge:ingest"))):
    knowledge_service.delete(db, doc_id)
    record_audit("admin.knowledge_delete", admin.id, details={"doc_id": str(doc_id)})
    return {"detail": "Document and its chunks removed"}


@router.post("/knowledge/fetch", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def fetch_knowledge(db: DB, data: FetchRequest | None = None, admin: User = Depends(require_permission("knowledge:ingest"))):
    """Download and index official documents: the URL in the body, or every entry in rag/sources.json."""
    from backend.workers.tasks import fetch_sources_task

    sources = [data.model_dump()] if data else None
    task = fetch_sources_task.delay(sources)
    record_audit("admin.knowledge_fetch", admin.id, details={"url": data.url if data else "manifest"})
    return {"detail": f"Fetch queued (task {task.id})"}


@router.get("/feedback", response_model=list[FeedbackAdminOut])
def list_feedback(
    db: DB,
    _: User = Depends(require_permission("audit:read")),
    disagreements_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """User verdicts on analyses; `disagrees` marks likely false positives / negatives to review."""
    return feedback_service.admin_list(db, disagreements_only, limit, offset)


@router.get("/feedback/export")
def export_feedback(db: DB, _: User = Depends(require_permission("audit:read"))):
    """Consented, labelled examples as JSON Lines - feed to `scripts/evaluate_risk.py --dataset`."""
    return StreamingResponse(
        feedback_service.export_jsonl(db),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=feedback.jsonl"},
    )


@router.get("/impact", tags=["Admin"])
def impact(db: DB, days: int = Query(default=30, ge=1, le=365), _: User = Depends(require_permission("users:read"))):
    """Aggregate, anonymous impact numbers for the last `days` days (no personal data)."""
    from datetime import UTC, timedelta

    from sqlalchemy import func

    from backend.models import HelpRequest, QuizAttempt, ScamAnalysis

    since = datetime.now(UTC) - timedelta(days=days)

    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    by_level = dict(
        db.execute(
            select(ScamAnalysis.risk_level, func.count())
            .where(ScamAnalysis.created_at >= since)
            .group_by(ScamAnalysis.risk_level)
        ).all()
    )
    quiz = db.execute(
        select(func.count(), func.avg(QuizAttempt.score * 100.0 / func.nullif(QuizAttempt.total, 0))).where(
            QuizAttempt.created_at >= since
        )
    ).one()
    by_language = dict(db.execute(select(User.language, func.count()).group_by(User.language)).all())
    return {
        "period_days": days,
        "users_total": count(User),
        "users_new": count(User, User.created_at >= since),
        "users_by_language": by_language,
        "checks_total": sum(by_level.values()),
        "checks_by_level": by_level,
        "high_risk_flagged": by_level.get("high", 0) + by_level.get("critical", 0),
        "reports_started": count(ScamAnalysis, ScamAnalysis.reported_at >= since),
        "family_alerts": count(HelpRequest, HelpRequest.created_at >= since),
        "quiz_attempts": quiz[0] or 0,
        "quiz_avg_percent": round(float(quiz[1]), 1) if quiz[1] is not None else None,
    }
