from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, false, true
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey


class EmergencyContact(UUIDPrimaryKey, CreatedAt, Base):
    """A trusted person who is alerted when the user presses Get Help or meets a dangerous scam."""

    __tablename__ = "emergency_contacts"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False, default="family")
    phone: Mapped[str] = mapped_column(String(20), nullable=False)  # E.164
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_on_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notified_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HelpRequest(UUIDPrimaryKey, CreatedAt, Base):
    """Record of a family alert (Get Help button or automatic high-risk alert)."""

    __tablename__ = "help_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)  # help_button | auto_high_risk
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("scam_analyses.id", ondelete="SET NULL"), nullable=True
    )
    results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class ReadinessItem(UUIDPrimaryKey, CreatedAt, Base):
    """Family-readiness checklist row: is there a nominee, does the family know where papers are?

    Deliberately holds no account numbers, amounts or nominee personal details - only statuses and a
    short, redacted note about where documents are kept.
    """

    __tablename__ = "readiness_items"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_readiness_items_user_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(30), nullable=False)  # bank_account | demat | will | ...
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    nominee: Mapped[str] = mapped_column(String(10), nullable=False, default="not_sure", server_default="not_sure")
    documents_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    family_informed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
