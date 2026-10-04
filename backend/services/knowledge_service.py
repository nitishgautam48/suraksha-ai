"""Admin management of the RAG knowledge base."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import KnowledgeDocument
from backend.rag import store
from backend.rag.fetcher import FetchError, Source, download, load_manifest, save_fetched
from backend.rag.ingest import ingest_document, origin_dir, register_file
from backend.utils.logging import get_logger

log = get_logger(__name__)


def _queue_ingest(doc_id: uuid.UUID) -> None:
    from backend.workers.tasks import ingest_document_task

    ingest_document_task.delay(str(doc_id))


def add_upload(
    db: Session, data: bytes, ext: str, title: str, source: str, url: str | None, topic: str, uploaded_by: uuid.UUID
) -> KnowledgeDocument:
    path = origin_dir("upload") / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    doc = register_file(
        db, path, "upload", {"title": title, "source": source, "url": url or "", "topic": topic, "uploaded_by": uploaded_by}
    )
    _queue_ingest(doc.id)
    return doc


def get_or_404(db: Session, doc_id: uuid.UUID) -> KnowledgeDocument:
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


def reingest(db: Session, doc_id: uuid.UUID) -> KnowledgeDocument:
    doc = get_or_404(db, doc_id)
    doc.status = "pending"
    db.commit()
    _queue_ingest(doc.id)
    return doc


def delete(db: Session, doc_id: uuid.UUID) -> None:
    doc = get_or_404(db, doc_id)
    if doc.origin == "bundled":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bundled documents ship with the app; edit backend/rag/knowledge instead"
        )
    try:
        store.delete_doc(doc.doc_key)
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Vector store unavailable: {exc}") from exc
    path = Path(doc.file_path)
    if path.resolve().is_relative_to(settings.KNOWLEDGE_UPLOAD_DIR.resolve()):
        path.unlink(missing_ok=True)
    db.delete(doc)
    db.commit()


def fetch_and_ingest(db: Session, sources: list[Source] | None = None) -> list[dict]:
    """Download each source (default: rag/sources.json), then index it. Runs on the Celery worker."""
    results = []
    for src in sources if sources is not None else load_manifest():
        try:
            data, file_type = download(src.url)
            path = save_fetched(src, data, file_type, origin_dir("fetched"))
            doc = register_file(
                db, path, "fetched", {"title": src.title, "source": src.source, "url": src.url, "topic": src.topic}
            )
            doc = ingest_document(db, doc)
            results.append({"url": src.url, "status": doc.status, "chunks": doc.chunks, "error": doc.error})
        except FetchError as exc:
            log.warning("Fetch failed for %s: %s", src.url, exc)
            results.append({"url": src.url, "status": "failed", "chunks": 0, "error": str(exc)})
    return results


def list_documents(db: Session) -> list[KnowledgeDocument]:
    return list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.origin, KnowledgeDocument.title)).all())
