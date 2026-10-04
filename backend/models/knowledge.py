from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey


class KnowledgeDocument(UUIDPrimaryKey, CreatedAt, Base):
    """A document indexed into the RAG vector store (bundled, uploaded by an admin, or fetched)."""

    __tablename__ = "knowledge_documents"

    doc_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)  # chunk metadata "doc"
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # md | txt | pdf | html
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    topic: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    origin: Mapped[str] = mapped_column(String(10), nullable=False, default="upload")  # bundled | upload | fetched
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", index=True)  # pending|ingested|failed
    chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
