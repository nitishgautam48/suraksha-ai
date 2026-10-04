from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey


class UploadedFile(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "uploaded_files"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # image | pdf | audio
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Set when the file bytes are deleted (right after text extraction); the row keeps only metadata.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScamAnalysis(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "scam_analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    safe_practices: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # When the user opened the "report to 1930 / cybercrime.gov.in" flow for this analysis.
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalysisFeedback(UUIDPrimaryKey, CreatedAt, Base):
    """User verdict on an analysis - the labelled data used to re-calibrate the risk engine."""

    __tablename__ = "analysis_feedback"
    __table_args__ = (UniqueConstraint("analysis_id", "user_id", name="uq_analysis_feedback_analysis_user"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scam_analyses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)  # scam | not_scam
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Explicit consent to include the (already truncated) message excerpt in the evaluation dataset.
    share_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
