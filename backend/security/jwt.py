"""JWT access / refresh tokens with Redis-backed revocation (logout)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.config import settings
from backend.utils.cache import get_redis
from backend.utils.logging import get_logger

log = get_logger(__name__)
ISSUER = "suraksha-ai"


class TokenError(Exception):
    pass


def _encode(sub: str, role: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "role": role,
        "type": token_type,
        "iat": now,
        "nbf": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
        "iss": ISSUER,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    return _encode(user_id, role, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: str, role: str) -> str:
    return _encode(user_id, role, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "type", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid token") from exc
    if payload.get("type") != expected_type:
        raise TokenError("Wrong token type")
    if is_revoked(payload["jti"]):
        raise TokenError("Token revoked")
    return payload


def revoke(payload: dict[str, Any]) -> None:
    ttl = max(int(payload["exp"] - datetime.now(UTC).timestamp()), 1)
    try:
        get_redis().set(f"suraksha:revoked:{payload['jti']}", "1", ex=ttl)
    except Exception as exc:  # pragma: no cover
        log.warning("Could not persist token revocation: %s", exc)


def is_revoked(jti: str) -> bool:
    try:
        return bool(get_redis().exists(f"suraksha:revoked:{jti}"))
    except Exception:
        return False
