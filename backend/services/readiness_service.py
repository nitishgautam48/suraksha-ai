"""Nominee & family-readiness checklist (education + record-keeping, never advice).

Elderly users and their families often lose track of where savings are and whether nominees are
recorded. This checklist asks, per type of holding, only: does it apply, is a nominee recorded,
does the family know where the papers are. No account numbers, amounts or nominee details.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import i18n
from backend.models import ReadinessItem
from backend.services.gamification_service import award
from backend.utils.redact import redact

ITEMS: tuple[tuple[str, str], ...] = (
    ("bank_account", "account_balance"),
    ("fixed_deposit", "savings"),
    ("demat", "monitoring"),
    ("mutual_fund", "pie_chart"),
    ("insurance", "health_and_safety"),
    ("epf", "work"),
    ("nps", "elderly"),
    ("post_office", "local_post_office"),
    ("locker", "lock"),
    ("property", "home"),
    ("will", "description"),
)
KEYS = {k for k, _ in ITEMS}


def _rows(db: Session, user_id: uuid.UUID) -> dict[str, ReadinessItem]:
    return {r.key: r for r in db.scalars(select(ReadinessItem).where(ReadinessItem.user_id == user_id))}


def _points(row: ReadinessItem | None) -> int:
    """0-4: nominee / will recorded (2), papers' location noted (1), family told (1)."""
    if row is None:
        return 0
    return 2 * (row.nominee == "yes") + bool(row.documents_location) + bool(row.family_informed)


def overview(db: Session, user_id: uuid.UUID, language: str) -> dict[str, Any]:
    rows = _rows(db, user_id)
    items, earned, possible = [], 0, 0
    for key, icon in ITEMS:
        row = rows.get(key)
        applicable = row.applicable if row else True
        if applicable:
            earned += _points(row)
            possible += 4
        items.append(
            {
                "key": key,
                "icon": icon,
                "title": i18n.t(f"rd_{key}_title", language),
                "tip": i18n.t(f"rd_{key}_tip", language),
                "applicable": applicable,
                "nominee": row.nominee if row else "not_sure",
                "documents_location": row.documents_location if row else None,
                "family_informed": bool(row and row.family_informed),
                "reviewed_at": row.reviewed_at if row else None,
                "done": bool(row) and applicable and _points(row) == 4,
            }
        )
    todo = [i for i in items if i["applicable"] and not i["done"]]
    return {
        "title": i18n.t("readiness_title", language),
        "intro": i18n.t("readiness_intro", language),
        "disclaimer": i18n.t("readiness_disclaimer", language),
        "extra_tip": i18n.t("readiness_udgam", language),
        "score_pct": round(100 * earned / possible) if possible else 100,
        "items": items,
        "next_steps": [{"key": i["key"], "title": i["title"], "tip": i["tip"]} for i in todo[:3]],
    }


def update(db: Session, user_id: uuid.UUID, key: str, changes: dict[str, Any]) -> None:
    if key not in KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown checklist item")
    row = _rows(db, user_id).get(key) or ReadinessItem(user_id=user_id, key=key)
    for field in ("applicable", "nominee", "family_informed"):
        if changes.get(field) is not None:
            setattr(row, field, changes[field])
    if "documents_location" in changes:
        note = (changes["documents_location"] or "").strip()
        row.documents_location = redact(note)[0][:160] if note else None
    row.reviewed_at = datetime.now(UTC)
    db.add(row)
    db.flush()
    award(db, user_id, "readiness_item", ref=key)
    db.commit()


def family_summary(db: Session, user_id: uuid.UUID, name: str, language: str) -> str:
    """Plain text the user can print or share with family: what exists and where papers are kept."""
    data = overview(db, user_id, language)
    yes, no, unsure = "✔", "✘", "?"
    lines = [f"{data['title']} - {name}", ""]
    for i in data["items"]:
        if not i["applicable"]:
            continue
        mark = {"yes": yes, "no": no}.get(i["nominee"], unsure)
        where = f" - {i['documents_location']}" if i["documents_location"] else ""
        lines.append(f"[{mark}] {i['title']}{where}")
    lines += ["", data["extra_tip"], "", data["disclaimer"]]
    return "\n".join(lines)
