"""Knowledge ingestion: Documents -> loaders -> chunking -> embeddings (Ollama) -> ChromaDB.

Every indexed document is tracked in the ``knowledge_documents`` table. Re-ingesting a document first
deletes its previous chunks, so edited or replaced files never leave stale passages behind.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.ai.ollama_client import get_ollama
from backend.config import settings
from backend.database.session import session_scope
from backend.models import KnowledgeDocument
from backend.rag import store
from backend.rag.chunker import chunk_markdown
from backend.rag.loaders import SUPPORTED, load_file
from backend.utils.logging import get_logger

log = get_logger(__name__)
BATCH = 16
_PAGE = re.compile(r"^Page (\d+)$")


def ingest_body(doc_key: str, body: str, meta: dict) -> int:
    """Replace all chunks for ``doc_key`` with fresh embeddings of ``body``."""
    chunks = chunk_markdown(body, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
    store.delete_doc(doc_key)
    if not chunks:
        return 0
    ollama = get_ollama()
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        # nomic-embed-text expects task prefixes for best retrieval quality.
        vectors = ollama.embed([f"search_document: {c.text}" for c in batch])
        store.upsert(
            ids=[f"{doc_key}#{c.index}-{hashlib.sha256(c.text.encode()).hexdigest()[:10]}" for c in batch],
            embeddings=vectors,
            documents=[c.text for c in batch],
            metadatas=[
                {
                    "doc": doc_key,
                    "title": meta.get("title") or doc_key,
                    "source": meta.get("source") or "Suraksha AI",
                    "url": meta.get("url") or "",
                    "topic": meta.get("topic") or "general",
                    "section": c.section,
                    "page": int(m.group(1)) if (m := _PAGE.match(c.section)) else 0,
                    "chunk": c.index,
                }
                for c in batch
            ],
        )
    return len(chunks)


def ingest_document(db: Session, doc: KnowledgeDocument) -> KnowledgeDocument:
    """Load, chunk, embed and index one tracked document, recording the outcome on the row."""
    path = Path(doc.file_path)
    try:
        loaded = load_file(path)
        if not loaded.body.strip():
            raise ValueError("No extractable text (scanned PDF without OCR, or empty file)")
        meta = {"title": doc.title, "source": doc.source, "url": doc.url or "", "topic": doc.topic}
        doc.chunks = ingest_body(doc.doc_key, loaded.body, meta)
        doc.pages = loaded.pages
        doc.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        doc.status, doc.error, doc.ingested_at = "ingested", None, datetime.now(UTC)
        log.info("Ingested %s (%d chunks)", doc.doc_key, doc.chunks)
    except Exception as exc:
        doc.status, doc.error = "failed", str(exc)[:2000]
        log.warning("Ingestion failed for %s: %s", doc.doc_key, exc)
    db.commit()
    return doc


def register_file(db: Session, path: Path, origin: str, overrides: dict | None = None) -> KnowledgeDocument:
    """Create or update the tracking row for a file on disk (metadata: front matter < sidecar < overrides)."""
    loaded_meta = {}
    try:
        loaded_meta = load_file(path).meta
    except Exception as exc:
        log.debug("Could not pre-read metadata for %s: %s", path, exc)
    meta = {**loaded_meta, **(overrides or {})}
    doc_key = f"{origin}/{path.name}"
    doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.doc_key == doc_key))
    if doc is None:
        doc = KnowledgeDocument(doc_key=doc_key, origin=origin)
        db.add(doc)
    doc.file_path = str(path)
    doc.file_type = SUPPORTED[path.suffix.lower()]
    doc.title = (meta.get("title") or path.stem.replace("_", " ").title())[:300]
    doc.source = (meta.get("source") or "Unknown source")[:200]
    doc.url = (meta.get("url") or None) and meta["url"][:1000]
    doc.topic = (meta.get("topic") or "general")[:40]
    if overrides and overrides.get("uploaded_by"):
        doc.uploaded_by = overrides["uploaded_by"]
    doc.status = "pending"
    db.commit()
    return doc


def _files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)


def origin_dir(origin: str) -> Path:
    if origin == "bundled":
        return settings.KNOWLEDGE_DIR
    path = settings.KNOWLEDGE_UPLOAD_DIR / ("uploads" if origin == "upload" else "fetched")
    path.mkdir(parents=True, exist_ok=True)
    return path


def ingest_directory(directory: Path | None = None, origin: str | None = None) -> dict[str, int]:
    """Index the bundled knowledge folder and the upload folder (or one specific directory)."""
    targets = [(directory, origin or "upload")] if directory else [(origin_dir(o), o) for o in ("bundled", "upload", "fetched")]
    results: dict[str, int] = {}
    with session_scope() as db:
        for folder, org in targets:
            for path in _files(folder):
                existing = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.doc_key == f"{org}/{path.name}"))
                overrides = (
                    {"title": existing.title, "source": existing.source, "url": existing.url or "", "topic": existing.topic}
                    if existing and org != "bundled"
                    else None
                )
                doc = ingest_document(db, register_file(db, path, org, overrides))
                results[doc.doc_key] = doc.chunks if doc.status == "ingested" else -1
    return results
