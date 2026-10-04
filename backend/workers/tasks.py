"""Background jobs: async file scans, knowledge ingestion, daily behavioural nudges."""

from __future__ import annotations

import json
import uuid

from celery.signals import worker_ready
from fastapi import HTTPException

from backend.ai.ollama_client import get_ollama
from backend.config import settings
from backend.database.session import session_scope
from backend.models import UploadedFile
from backend.rag import store
from backend.rag.ingest import ingest_directory
from backend.utils.logging import configure_logging, get_logger
from backend.workers.celery_app import celery_app

configure_logging()
log = get_logger(__name__)


@celery_app.task(name="suraksha.process_scan_file", bind=True, max_retries=2)
def process_scan_file(self, file_id: str, language: str = "en") -> dict:
    from backend.services.scan_service import process_file

    with session_scope() as db:
        record = db.get(UploadedFile, uuid.UUID(file_id))
        if record is None:
            return {"status": "error", "detail": "file not found"}
        try:
            result = process_file(db, record, language)
        except HTTPException as exc:
            return {"status": "error", "detail": exc.detail, "status_code": exc.status_code}
    return {"status": "done", "result": json.loads(json.dumps(result, default=str))}


@celery_app.task(
    name="suraksha.send_email", bind=True, autoretry_for=(Exception,), retry_backoff=30, retry_kwargs={"max_retries": 5}
)
def send_email_task(self, to: str, subject: str, text: str, html_body: str | None = None) -> str:
    from backend.services.email_service import send_email_now

    send_email_now(to, subject, text, html_body)
    return "sent"


@celery_app.task(
    name="suraksha.send_sms", bind=True, autoretry_for=(Exception,), retry_backoff=20, retry_kwargs={"max_retries": 3}
)
def send_sms_task(self, to: str, text: str, purpose: str, variables: dict | None = None) -> str:
    from backend.services.sms_service import send_sms_now

    send_sms_now(to, text, purpose, variables)
    return "sent"


@celery_app.task(name="suraksha.ingest_knowledge")
def ingest_knowledge() -> dict:
    return ingest_directory()


@celery_app.task(name="suraksha.ingest_document")
def ingest_document_task(doc_id: str) -> dict:
    from backend.models import KnowledgeDocument
    from backend.rag.ingest import ingest_document

    with session_scope() as db:
        doc = db.get(KnowledgeDocument, uuid.UUID(doc_id))
        if doc is None:
            return {"status": "missing"}
        doc = ingest_document(db, doc)
        return {"status": doc.status, "chunks": doc.chunks, "error": doc.error}


@celery_app.task(name="suraksha.fetch_sources")
def fetch_sources_task(sources: list[dict] | None = None) -> list[dict]:
    from backend.rag.fetcher import Source
    from backend.services.knowledge_service import fetch_and_ingest

    with session_scope() as db:
        return fetch_and_ingest(db, [Source(**s) for s in sources] if sources is not None else None)


@celery_app.task(name="suraksha.ensure_knowledge_base")
def ensure_knowledge_base() -> str:
    """Ingest the bundled knowledge base once the embedding model has been pulled."""
    if not settings.RAG_AUTO_INGEST:
        return "disabled"
    n = store.count()
    if n < 0:
        return "chroma-unavailable"
    if n > 0:
        return f"ready ({n} chunks)"
    if not get_ollama().has_model(settings.OLLAMA_EMBED_MODEL):
        return "waiting-for-embedding-model"
    res = ingest_directory()
    return f"ingested {sum(res.values())} chunks"


@celery_app.task(name="suraksha.daily_nudges")
def daily_nudges() -> int:
    from backend.services.maintenance_service import send_daily_nudges

    with session_scope() as db:
        return send_daily_nudges(db)


@celery_app.task(name="suraksha.purge_expired_scans")
def purge_expired_scans() -> int:
    from backend.services.maintenance_service import purge_expired_scans as purge

    with session_scope() as db:
        return purge(db)


@celery_app.task(name="suraksha.weekly_reports")
def weekly_reports() -> int:
    from backend.services.maintenance_service import send_weekly_reports

    with session_scope() as db:
        return send_weekly_reports(db)


@worker_ready.connect
def _on_worker_ready(sender=None, **_):
    ensure_knowledge_base.delay()
