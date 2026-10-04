from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey


class ChatHistory(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "chat_history"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False, default="text")  # text | voice
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class SafetyAlert(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "safety_alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("scam_analyses.id", ondelete="SET NULL"), nullable=True
    )


class AuditLog(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class UserActivity(UUIDPrimaryKey, CreatedAt, Base):
    """One row per (user, day, kind) - drives learning streaks and awareness trends."""

    __tablename__ = "user_activity"
    __table_args__ = (UniqueConstraint("user_id", "activity_date", "kind", name="uq_user_activity_day_kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # lesson | quiz | scan | chat | habit
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class HabitChecklistItem(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "habit_checklist"
    __table_args__ = (UniqueConstraint("user_id", "item_key", name="uq_habit_checklist_user_item"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_key: Mapped[str] = mapped_column(String(60), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavingsCheckin(UUIDPrimaryKey, CreatedAt, Base):
    """Weekly yes/no savings-discipline check-in. No amounts or products are recorded."""

    __tablename__ = "savings_checkins"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_savings_checkins_user_week"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
