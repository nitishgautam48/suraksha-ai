"""Redis helpers. Every call degrades gracefully when Redis is unreachable."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis

from backend.config import settings
from backend.utils.logging import get_logger

log = get_logger(__name__)
_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
    return _client


def cache_key(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"suraksha:{prefix}:{digest}"


def cache_get(key: str) -> Any | None:
    try:
        raw = get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:  # pragma: no cover - infra failure path
        log.debug("cache_get failed: %s", exc)
        return None


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        get_redis().set(key, json.dumps(value, default=str), ex=ttl or settings.CACHE_TTL_SECONDS)
    except Exception as exc:  # pragma: no cover
        log.debug("cache_set failed: %s", exc)


def redis_ping() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


def task_owner_key(task_id: str) -> str:
    return f"suraksha:task-owner:{task_id}"
