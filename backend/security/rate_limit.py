"""Redis-backed rate limiting (slowapi). Keyed by authenticated user, falling back to client IP."""

from __future__ import annotations

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from backend.config import settings


def rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            payload = jwt.decode(
                auth[7:], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"verify_exp": False}
            )
            return f"user:{payload.get('sub')}"
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=settings.REDIS_URL if settings.RATE_LIMIT_ENABLED else "memory://",
    enabled=settings.RATE_LIMIT_ENABLED,
    swallow_errors=True,
    in_memory_fallback_enabled=True,
    headers_enabled=False,
)
