"""XP, levels and achievements. Rewards learning and safe behaviour - never trading or investing."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    AnalysisFeedback,
    Course,
    EmergencyContact,
    HabitChecklistItem,
    LearningProgress,
    QuizAttempt,
    ScamAnalysis,
    User,
    UserAchievement,
    UserActivity,
    XPEvent,
)
from backend.models.enums import AlertSeverity, AlertType
from backend.utils.logging import get_logger

log = get_logger(__name__)

LEVELS: list[tuple[int, str]] = [
    (0, "Beginner"),
    (100, "Learner"),
    (300, "Aware"),
    (700, "Alert"),
    (1200, "Defender"),
    (2000, "Guardian"),
    (3000, "Protector"),
    (4500, "Sentinel"),
    (6500, "Champion"),
    (9000, "Suraksha Hero"),
]

# action -> (xp, max awards per day or None for "once per ref")
XP_RULES: dict[str, tuple[int, int | None]] = {
    "lesson_complete": (50, None),
    "quiz_correct": (20, None),  # once per question, first time correct
    "quiz_pass": (100, None),  # once per course
    "flashcards": (15, None),  # ref = course:date
    "daily_learning": (25, None),  # ref = date
    "scan": (10, 5),
    "chat": (5, 3),
    "checklist_item": (30, None),
    "savings_week": (20, None),
    "feedback": (5, None),
    "trusted_contact": (50, None),
    "verify_email": (50, None),
    "verify_phone": (50, None),
    "report": (20, None),  # opened the report-to-1930 flow for a risky result
    "readiness_item": (15, None),  # nominee / family-readiness checklist item reviewed
    "badge": (0, None),  # xp set per achievement
}

ACTION_TITLES = {
    "lesson_complete": ("school", "p", "Completed a lesson"),
    "quiz_correct": ("quiz", "p", "Answered a quiz question correctly"),
    "quiz_pass": ("emoji_events", "a", "Passed a course assessment"),
    "flashcards": ("style", "p", "Practised flash cards"),
    "daily_learning": ("local_fire_department", "a", "Kept the learning streak alive"),
    "scan": ("gpp_maybe", "r", "Checked a message before acting"),
    "chat": ("forum", "p", "Asked the safety assistant"),
    "checklist_item": ("savings", "g", "Emergency-fund step completed"),
    "savings_week": ("savings", "g", "Saved this week"),
    "feedback": ("rate_review", "p", "Helped improve detection"),
    "trusted_contact": ("family_restroom", "g", "Added a trusted contact"),
    "verify_email": ("verified", "g", "Verified email"),
    "verify_phone": ("verified", "g", "Verified phone"),
    "report": ("campaign", "r", "Reported a scam"),
    "readiness_item": ("family_restroom", "g", "Updated the family-readiness checklist"),
    "badge": ("workspace_premium", "a", "Claimed a badge"),
}


def level_for(xp: int) -> dict[str, Any]:
    idx = max(i for i, (threshold, _) in enumerate(LEVELS) if xp >= threshold)
    cur_xp, name = LEVELS[idx]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    progress = 100.0 if nxt is None else round((xp - cur_xp) / (nxt - cur_xp) * 100, 1)
    return {
        "xp": xp,
        "level": idx + 1,
        "level_name": name,
        "label": f"Level {idx + 1} · {name}",
        "current_level_xp": cur_xp,
        "next_level_xp": nxt,
        "xp_to_next": (nxt - xp) if nxt else 0,
        "progress_pct": progress,
    }


# ---- achievements -------------------------------------------------------------------------------
def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _threats(db, uid):
    return _count(
        db,
        select(func.count())
        .select_from(ScamAnalysis)
        .where(ScamAnalysis.user_id == uid, ScamAnalysis.risk_level.in_(("high", "critical"))),
    )


def _lessons_done(db, uid):
    rows = db.scalars(select(LearningProgress.completed_lessons).where(LearningProgress.user_id == uid)).all()
    return sum(len(r or []) for r in rows)


def _courses_done(db, uid):
    return _count(
        db,
        select(func.count())
        .select_from(LearningProgress)
        .where(LearningProgress.user_id == uid, LearningProgress.completion >= 100),
    )


def _total_courses(db):
    return max(_count(db, select(func.count()).select_from(Course).where(Course.is_published.is_(True))), 1)


def _streak(db, uid):
    from backend.services.activity_service import streaks

    return max(streaks(db, uid))


def _savings_streak(db, uid):
    from backend.services.habit_service import _savings

    return _savings(db, uid)[1]


def _checklist_done(db, uid):
    from backend.services.habit_service import EMERGENCY_FUND_CHECKLIST

    done = _count(
        db,
        select(func.count())
        .select_from(HabitChecklistItem)
        .where(HabitChecklistItem.user_id == uid, HabitChecklistItem.completed.is_(True)),
    )
    return 1 if done >= len(EMERGENCY_FUND_CHECKLIST) else 0


@dataclass(frozen=True)
class Achievement:
    key: str
    title: str
    description: str
    icon: str
    tone: str
    target: int
    bonus_xp: int
    metric: Callable[[Session, uuid.UUID], int]


ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement(
        "first_check",
        "First Check",
        "Checked your first message",
        "search_check",
        "p",
        1,
        20,
        lambda db, u: _count(db, select(func.count()).select_from(ScamAnalysis).where(ScamAnalysis.user_id == u)),
    ),
    Achievement("scam_spotter", "Scam Spotter", "Flagged 10 risky messages", "search_check", "r", 10, 150, _threats),
    Achievement("scam_buster", "Scam Buster", "Flagged 25 risky messages", "gpp_bad", "r", 25, 300, _threats),
    Achievement("week_warrior", "Week Warrior", "7-day learning streak", "local_fire_department", "a", 7, 100, _streak),
    Achievement("month_master", "Month Master", "30-day learning streak", "local_fire_department", "a", 30, 400, _streak),
    Achievement("financial_learner", "Financial Learner", "Finish 10 lessons", "school", "a", 10, 150, _lessons_done),
    Achievement("graduate", "Graduate", "Complete a full course", "workspace_premium", "p", 1, 100, _courses_done),
    Achievement("scholar", "Scholar", "Complete every course", "military_tech", "v", 4, 400, _courses_done),
    Achievement(
        "quiz_ace",
        "Quiz Ace",
        "Score 100% on an assessment",
        "emoji_events",
        "a",
        1,
        100,
        lambda db, u: _count(
            db,
            select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == u, QuizAttempt.score == QuizAttempt.total),
        ),
    ),
    Achievement("consistent_saver", "Consistent Saver", "Saved 8 weeks in a row", "savings", "g", 8, 200, _savings_streak),
    Achievement(
        "emergency_ready",
        "Emergency Ready",
        "Completed the emergency-fund checklist",
        "health_and_safety",
        "g",
        1,
        200,
        _checklist_done,
    ),
    Achievement(
        "family_shield",
        "Family Shield",
        "Added a trusted contact",
        "family_restroom",
        "g",
        1,
        50,
        lambda db, u: _count(db, select(func.count()).select_from(EmergencyContact).where(EmergencyContact.user_id == u)),
    ),
    Achievement(
        "helper",
        "Community Helper",
        "Gave feedback on 5 analyses",
        "rate_review",
        "p",
        5,
        75,
        lambda db, u: _count(db, select(func.count()).select_from(AnalysisFeedback).where(AnalysisFeedback.user_id == u)),
    ),
)
BY_KEY = {a.key: a for a in ACHIEVEMENTS}


def check_achievements(db: Session, user_id: uuid.UUID) -> list[str]:
    """Unlock any newly-earned achievements (they then await claiming). Returns new keys."""
    from backend.services.alert_service import create_alert

    owned = set(db.scalars(select(UserAchievement.key).where(UserAchievement.user_id == user_id)).all())
    new = []
    for a in ACHIEVEMENTS:
        if a.key in owned:
            continue
        if a.key == "scholar":
            target = _total_courses(db)
        else:
            target = a.target
        if a.metric(db, user_id) >= target:
            db.add(UserAchievement(user_id=user_id, key=a.key))
            create_alert(
                db,
                user_id,
                AlertType.ACHIEVEMENT,
                f"Badge unlocked: {a.title}",
                f"{a.description}. Claim it for +{a.bonus_xp} XP.",
                AlertSeverity.INFO,
            )
            new.append(a.key)
    if new:
        db.flush()
    return new


# ---- awarding -----------------------------------------------------------------------------------
def award(db: Session, user_id: uuid.UUID, action: str, ref: str | None = None, xp: int | None = None, check: bool = True) -> int:
    """Grant XP once per (action, ref); daily-capped actions use the date. Returns XP granted (0 if not)."""
    base_xp, daily_cap = XP_RULES[action]
    xp = base_xp if xp is None else xp
    if daily_cap is not None:
        today = date.today().isoformat()
        start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
        n_today = _count(
            db,
            select(func.count())
            .select_from(XPEvent)
            .where(XPEvent.user_id == user_id, XPEvent.action == action, XPEvent.created_at >= start),
        )
        if n_today >= daily_cap:
            return 0
        ref = f"{today}:{n_today + 1}"
    ref = str(ref or "once")[:120]
    if db.scalar(select(XPEvent.id).where(XPEvent.user_id == user_id, XPEvent.action == action, XPEvent.ref == ref)):
        return 0
    try:
        with db.begin_nested():
            db.add(XPEvent(user_id=user_id, action=action, ref=ref, xp=xp))
    except IntegrityError:  # concurrent duplicate
        return 0
    user = db.get(User, user_id)
    if user is not None:
        user.xp = (user.xp or 0) + xp
    if check:
        check_achievements(db, user_id)
    return xp


def claim(db: Session, user_id: uuid.UUID, key: str) -> dict[str, Any]:
    a = BY_KEY.get(key)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown achievement")
    ua = db.scalar(select(UserAchievement).where(UserAchievement.user_id == user_id, UserAchievement.key == key))
    if ua is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Achievement not unlocked yet")
    if ua.claimed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already claimed")
    ua.claimed_at = datetime.now(UTC)
    gained = award(db, user_id, "badge", ref=key, xp=a.bonus_xp)
    db.commit()
    return {"key": key, "xp_awarded": gained, **level_for(db.get(User, user_id).xp)}


def achievements(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    owned = {ua.key: ua for ua in db.scalars(select(UserAchievement).where(UserAchievement.user_id == user_id)).all()}
    out = []
    for a in ACHIEVEMENTS:
        target = _total_courses(db) if a.key == "scholar" else a.target
        ua = owned.get(a.key)
        state = "earned" if ua and ua.claimed_at else "claim" if ua else "locked"
        progress = min(a.metric(db, user_id), target) if state == "locked" else target
        out.append(
            {
                "key": a.key,
                "title": a.title,
                "description": a.description,
                "icon": a.icon,
                "tone": a.tone,
                "state": state,
                "progress": progress,
                "target": target,
                "bonus_xp": a.bonus_xp,
                "unlocked_at": ua.created_at if ua else None,
                "claimed_at": ua.claimed_at if ua else None,
            }
        )
    return out


def overview(db: Session, user: User) -> dict[str, Any]:
    recent = db.scalars(select(XPEvent).where(XPEvent.user_id == user.id).order_by(XPEvent.created_at.desc()).limit(10)).all()
    return {
        **level_for(user.xp or 0),
        "achievements": achievements(db, user.id),
        "recent_xp": [
            {
                "action": e.action,
                "title": ACTION_TITLES.get(e.action, ("", "", e.action))[2],
                "xp": e.xp,
                "created_at": e.created_at,
            }
            for e in recent
        ],
    }


# ---- activity views -----------------------------------------------------------------------------
def heatmap(db: Session, user_id: uuid.UUID, weeks: int = 14) -> dict[str, Any]:
    """Daily activity counts for the last N weeks (Monday-aligned), bucketed into levels 0-4."""
    today = date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    rows = db.execute(
        select(UserActivity.activity_date, func.sum(UserActivity.count))
        .where(UserActivity.user_id == user_id, UserActivity.activity_date >= start)
        .group_by(UserActivity.activity_date)
    ).all()
    counts = {d: int(n) for d, n in rows}
    days = []
    for i in range(weeks * 7):
        d = start + timedelta(days=i)
        n = counts.get(d, 0)
        days.append(
            {
                "date": d,
                "count": n,
                "level": 0 if n == 0 else 1 if n < 2 else 2 if n < 4 else 3 if n < 7 else 4,
                "future": d > today,
            }
        )
    return {"weeks": weeks, "start": start, "days": days, "active_days": sum(1 for d in days if d["count"])}


def recent_activity(db: Session, user_id: uuid.UUID, limit: int = 10) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for e in db.scalars(
        select(XPEvent)
        .where(XPEvent.user_id == user_id, XPEvent.action != "scan")
        .order_by(XPEvent.created_at.desc())
        .limit(limit)
    ).all():
        icon, tone, title = ACTION_TITLES.get(e.action, ("bolt", "p", e.action))
        if e.action == "badge" and e.ref in BY_KEY:
            title = f"Earned badge: {BY_KEY[e.ref].title}"
        items.append({"icon": icon, "tone": tone, "title": title, "meta": f"+{e.xp} XP", "time": e.created_at})
    for a in db.scalars(
        select(ScamAnalysis).where(ScamAnalysis.user_id == user_id).order_by(ScamAnalysis.created_at.desc()).limit(limit)
    ).all():
        tone = {"critical": "r", "high": "r", "medium": "a"}.get(a.risk_level, "g")
        items.append(
            {
                "icon": "gpp_bad" if tone == "r" else "gpp_maybe" if tone == "a" else "verified_user",
                "tone": tone,
                "title": f"Scanned a {a.platform or a.source_type} {'post' if a.source_type == 'social' else 'message'}",
                "meta": f"{a.risk_level.title()} risk · {a.risk_score}/100",
                "time": a.created_at,
            }
        )

    def key(i):
        t = i["time"]
        return t if t.tzinfo else t.replace(tzinfo=UTC)

    return sorted(items, key=key, reverse=True)[:limit]
