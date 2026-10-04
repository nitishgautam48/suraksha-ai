"""One-time passcodes for phone login / phone linking, stored (hashed) in Redis with a TTL.

Fails closed: if Redis is unreachable, OTP flows return 503 instead of skipping their limits.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from fastapi import HTTPException, status

from backend.config import settings
from backend.utils.cache import get_redis
from backend.utils.logging import get_logger

log = get_logger(__name__)
IP_MAX_PER_HOUR = 20


def _hash(phone: str, purpose: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{purpose}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _redis():
    r = get_redis()
    try:
        r.ping()
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OTP service temporarily unavailable") from exc
    return r


def _limit(r, key: str, limit: int, window: int) -> bool:
    n = r.incr(key)
    if n == 1:
        r.expire(key, window)
    return n <= limit


def issue(phone: str, purpose: str, ip: str | None) -> str:
    """Create and store an OTP; returns the plain code for delivery. Raises 429 when rate-limited."""
    r = _redis()
    if not r.set(f"suraksha:otp-cooldown:{purpose}:{phone}", "1", nx=True, ex=settings.OTP_RESEND_COOLDOWN_SECONDS):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Please wait {settings.OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting another code",
        )
    if not _limit(r, f"suraksha:otp-hour:{phone}", settings.OTP_MAX_PER_HOUR, 3600) or (
        ip and not _limit(r, f"suraksha:otp-hour-ip:{ip}", IP_MAX_PER_HOUR, 3600)
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many codes requested. Try again in an hour.")
    code = "".join(secrets.choice("0123456789") for _ in range(settings.OTP_LENGTH))
    r.set(
        f"suraksha:otp:{purpose}:{phone}",
        json.dumps({"h": _hash(phone, purpose, code), "attempts": 0}),
        ex=settings.OTP_TTL_SECONDS,
    )
    return code


def verify(phone: str, purpose: str, code: str) -> None:
    """Burn the OTP on success; count failures and invalidate after OTP_MAX_ATTEMPTS. Raises 400."""
    r = _redis()
    key = f"suraksha:otp:{purpose}:{phone}"
    raw = r.get(key)
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expired or not requested. Request a new code.")
    data = json.loads(raw)
    if hmac.compare_digest(data["h"], _hash(phone, purpose, code or "")):
        r.delete(key)
        return
    data["attempts"] += 1
    if data["attempts"] >= settings.OTP_MAX_ATTEMPTS:
        r.delete(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Too many wrong attempts. Request a new code.")
    ttl = max(r.ttl(key), 1)
    r.set(key, json.dumps(data), ex=ttl)
    left = settings.OTP_MAX_ATTEMPTS - data["attempts"]
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Incorrect code. {left} attempt(s) left.")
