from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey


class XPEvent(UUIDPrimaryKey, CreatedAt, Base):
    """An XP award. (user, action, ref) is unique so the same deed never pays twice."""

    __tablename__ = "xp_events"
    __table_args__ = (UniqueConstraint("user_id", "action", "ref", name="uq_xp_events_user_action_ref"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    ref: Mapped[str] = mapped_column(String(120), nullable=False)
    xp: Mapped[int] = mapped_column(Integer, nullable=False)


class UserAchievement(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_achievements_user_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
