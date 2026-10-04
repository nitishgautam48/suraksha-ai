from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid, false, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey, utcnow
from backend.models.enums import Language, Role


class User(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)  # E.164
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(60), nullable=True)  # Indian state / UT (utils/india.py)
    user_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # first_time_investor | student | ...
    # see services/preferences.py
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")  # cached sum of xp_events
    language: Mapped[str] = mapped_column(String(8), nullable=False, default=Language.EN.value)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.USER.value, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="password")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # JWTs issued before this instant are rejected (set on password reset/change: "log out everywhere").
    tokens_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Privacy-notice version the user accepted, and when (see GET /privacy).
    consent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class AuthToken(UUIDPrimaryKey, CreatedAt, Base):
    """Single-use, expiring tokens for email verification and password reset.

    Only the SHA-256 hash of the token is stored, so a database leak does not expose usable links.
    """

    __tablename__ = "auth_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # verify_email | reset_password
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
