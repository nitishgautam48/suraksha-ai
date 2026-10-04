"""Persistent audit trail. Failures to audit never break the request."""

from __future__ import annotations

import uuid
from typing import Any

from backend.database.session import SessionLocal
from backend.models import AuditLog
from backend.utils.logging import get_logger, request_id_ctx
from backend.utils.metrics import AUTH_EVENTS

log = get_logger(__name__)


def _to_uuid(value: Any) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def record_audit(action: str, user_id: Any = None, **fields: Any) -> None:
    if action.startswith("auth."):
        AUTH_EVENTS.labels(action.removeprefix("auth.")).inc()
    fields.setdefault("request_id", request_id_ctx.get())
    if fields.get("user_agent"):
        fields["user_agent"] = fields["user_agent"][:300]
    db = SessionLocal()
    try:
        db.add(AuditLog(action=action, user_id=_to_uuid(user_id), details=fields.pop("details", {}) or {}, **fields))
        db.commit()
    except Exception as exc:
        db.rollback()
        log.warning("audit write failed (%s): %s", action, exc)
    finally:
        db.close()
