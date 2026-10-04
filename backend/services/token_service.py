"""Single-use, hashed, expiring tokens for email verification and password reset."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import AuthToken, User
from backend.models.enums import TokenPurpose


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def issue(db: Session, user_id: uuid.UUID, purpose: TokenPurpose, ttl: timedelta) -> str:
    """Create a token, invalidating any earlier unused token for the same purpose. Returns the raw token."""
    now = datetime.now(UTC)
    db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user_id, AuthToken.purpose == purpose.value, AuthToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user_id, purpose=purpose.value, token_hash=_hash(raw), expires_at=now + ttl))
    db.commit()
    return raw


def consume(db: Session, raw: str, purpose: TokenPurpose) -> User:
    """Validate and burn a token. Raises 400 for unknown, used, expired or wrong-purpose tokens."""
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "This link is invalid or has expired. Please request a new one.")
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == _hash(raw)))
    now = datetime.now(UTC)
    if token is None or token.purpose != purpose.value or token.used_at is not None or _aware(token.expires_at) < now:
        raise invalid
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise invalid
    token.used_at = now
    return user
