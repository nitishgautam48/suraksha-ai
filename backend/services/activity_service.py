"""Daily activity tracking -> learning streaks."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import UserActivity

LEARNING_KINDS = ("lesson", "quiz", "flashcards")


def record_activity(db: Session, user_id: uuid.UUID, kind: str, when: date | None = None) -> None:
    when = when or date.today()
    row = db.scalar(
        select(UserActivity).where(UserActivity.user_id == user_id, UserActivity.activity_date == when, UserActivity.kind == kind)
    )
    if row:
        row.count += 1
    else:
        db.add(UserActivity(user_id=user_id, activity_date=when, kind=kind, count=1))


def _active_days(db: Session, user_id: uuid.UUID, kinds: tuple[str, ...]) -> list[date]:
    rows = db.scalars(
        select(UserActivity.activity_date).where(UserActivity.user_id == user_id, UserActivity.kind.in_(kinds)).distinct()
    ).all()
    return sorted(set(rows))


def streaks(db: Session, user_id: uuid.UUID, kinds: tuple[str, ...] = LEARNING_KINDS) -> tuple[int, int]:
    """Return (current_streak, longest_streak) in days. A streak survives until the end of today."""
    days = _active_days(db, user_id, kinds)
    if not days:
        return 0, 0
    longest = run = 1
    for prev, cur in zip(days, days[1:], strict=False):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        longest = max(longest, run)
    today = date.today()
    current = 0
    if days[-1] >= today - timedelta(days=1):
        current = 1
        for prev, cur in zip(reversed(days[:-1]), reversed(days[1:]), strict=False):
            if cur - prev == timedelta(days=1):
                current += 1
            else:
                break
    return current, longest
