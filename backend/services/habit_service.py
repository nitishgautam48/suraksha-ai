"""Module 4: Financial Habit Coach - behavioural nudges only, never investment recommendations."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.ai import prompts
from backend.ai.guardrails import output_violates_policy
from backend.ai.ollama_client import LLMUnavailable, get_ollama
from backend.config import settings
from backend.models import (
    Course,
    HabitChecklistItem,
    LearningProgress,
    Lesson,
    QuizAttempt,
    SavingsCheckin,
    ScamAnalysis,
    User,
)
from backend.services.activity_service import record_activity, streaks
from backend.services.gamification_service import award
from backend.utils.cache import cache_get, cache_key, cache_set

EMERGENCY_FUND_CHECKLIST: list[dict[str, str]] = [
    {
        "key": "track_expenses",
        "title": "Track one month of essential expenses",
        "description": "Know your monthly essentials: rent, food, utilities, medicines, school fees.",
    },
    {
        "key": "set_target",
        "title": "Set your emergency fund target",
        "description": "A common guideline is 3 to 6 months of essential expenses.",
    },
    {
        "key": "separate_money",
        "title": "Keep emergency money separate",
        "description": "Keep it apart from daily spending so it is not used by accident, yet easy to access.",
    },
    {
        "key": "automate_saving",
        "title": "Automate a small monthly saving",
        "description": "A fixed transfer on salary day builds the fund without relying on willpower.",
    },
    {"key": "first_month", "title": "Save your first month of expenses", "description": "The first milestone - celebrate it!"},
    {
        "key": "three_months",
        "title": "Reach three months of expenses",
        "description": "You now have a meaningful cushion against shocks.",
    },
    {
        "key": "family_plan",
        "title": "Share your safety plan with family",
        "description": "Tell family where the emergency fund is and save helpline 1930 in everyone's phone.",
    },
]
CHECKLIST_KEYS = {i["key"] for i in EMERGENCY_FUND_CHECKLIST}
SCAM_TOPICS = ("scam_detection", "upi_frauds", "cyber_safety")


def week_start(d: date | None = None) -> date:
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def set_checklist_item(db: Session, user_id: uuid.UUID, key: str, completed: bool) -> None:
    if key not in CHECKLIST_KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown checklist item")
    row = db.scalar(select(HabitChecklistItem).where(HabitChecklistItem.user_id == user_id, HabitChecklistItem.item_key == key))
    if row is None:
        row = HabitChecklistItem(user_id=user_id, item_key=key)
        db.add(row)
    row.completed = completed
    row.completed_at = datetime.now(UTC) if completed else None
    record_activity(db, user_id, "habit")
    db.flush()
    if completed:
        award(db, user_id, "checklist_item", ref=key)
    db.commit()


def savings_checkin(db: Session, user_id: uuid.UUID, saved: bool, note: str | None) -> None:
    ws = week_start()
    row = db.scalar(select(SavingsCheckin).where(SavingsCheckin.user_id == user_id, SavingsCheckin.week_start == ws))
    if row is None:
        row = SavingsCheckin(user_id=user_id, week_start=ws, saved=saved, note=note)
        db.add(row)
    else:
        row.saved, row.note = saved, note
    record_activity(db, user_id, "habit")
    db.flush()
    if saved:
        award(db, user_id, "savings_week", ref=ws.isoformat())
    db.commit()


def set_emergency_fund(db: Session, user_id: uuid.UUID, target: int | None, saved: int | None) -> dict[str, Any]:
    """User-entered goal and amount saved so far (their own numbers; we never suggest products)."""
    user = db.get(User, user_id)
    ef = dict((user.preferences or {}).get("emergency_fund") or {})
    if target is not None:
        ef["target"] = target
    if saved is not None:
        ef["saved"] = saved
    user.preferences = {**(user.preferences or {}), "emergency_fund": ef}
    record_activity(db, user_id, "habit")
    db.commit()
    return _ef(user)


def _ef(user: User) -> dict[str, Any] | None:
    ef = (user.preferences or {}).get("emergency_fund")
    if not ef or not ef.get("target"):
        return None
    saved = ef.get("saved") or 0
    return {"target": ef["target"], "saved": saved, "pct": round(min(saved / ef["target"] * 100, 100), 1)}


def _checklist(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    done = {r.item_key: r.completed for r in db.scalars(select(HabitChecklistItem).where(HabitChecklistItem.user_id == user_id))}
    return [{**item, "completed": done.get(item["key"], False)} for item in EMERGENCY_FUND_CHECKLIST]


def _savings(db: Session, user_id: uuid.UUID) -> tuple[float, int, list[dict[str, Any]]]:
    since = week_start() - timedelta(weeks=11)
    rows = db.scalars(
        select(SavingsCheckin)
        .where(SavingsCheckin.user_id == user_id, SavingsCheckin.week_start >= since)
        .order_by(SavingsCheckin.week_start.desc())
    ).all()
    if not rows:
        return 0.0, 0, []
    discipline = round(sum(r.saved for r in rows) / len(rows) * 100, 1)
    by_week = {r.week_start: r.saved for r in rows}
    streak, ws = 0, week_start()
    if ws not in by_week:  # the current week isn't over yet
        ws -= timedelta(weeks=1)
    while by_week.get(ws):
        streak += 1
        ws -= timedelta(weeks=1)
    return discipline, streak, [{"week_start": r.week_start, "saved": r.saved} for r in rows]


def scam_awareness(db: Session, user_id: uuid.UUID) -> float:
    rows = (
        db.execute(
            select(LearningProgress.completion)
            .join(Course, Course.id == LearningProgress.course_id)
            .where(LearningProgress.user_id == user_id, Course.topic.in_(SCAM_TOPICS))
        )
        .scalars()
        .all()
    )
    total_courses = (
        db.scalar(select(func.count()).select_from(Course).where(Course.topic.in_(SCAM_TOPICS), Course.is_published.is_(True)))
        or 1
    )
    completion = sum(rows) / total_courses
    quiz_avg = db.scalar(
        select(func.avg(QuizAttempt.score * 100.0 / QuizAttempt.total))
        .join(Course, Course.id == QuizAttempt.course_id)
        .where(QuizAttempt.user_id == user_id, Course.topic.in_(SCAM_TOPICS))
    )
    if quiz_avg is None:
        return round(completion, 1)
    return round(0.6 * completion + 0.4 * float(quiz_avg), 1)


def build_nudges(
    streak: int, ef_progress: float, saved_this_week: bool | None, awareness: float, recent_high_risk: bool
) -> list[str]:
    nudges: list[str] = []
    if recent_high_risk:
        nudges.append("You recently checked a risky message. Share the 1930 cyber-fraud helpline with your family today.")
    if ef_progress < 100:
        nudges.append("Building an emergency fund can improve financial resilience.")
    if saved_this_week is None:
        nudges.append("Have you set aside some savings this week? Small, regular amounts build discipline.")
    elif saved_this_week:
        nudges.append("Great job saving this week - consistency matters more than the amount.")
    if streak == 0:
        nudges.append("A 4-minute lesson today starts a new learning streak.")
    elif streak >= 3:
        nudges.append(f"You're on a {streak}-day learning streak. Keep it alive with one flash-card round.")
    if awareness < 50:
        nudges.append("Learn the top 5 UPI scam tricks - it takes less than 5 minutes.")
    return nudges[:4]


def ai_nudge(user_id: uuid.UUID, context: str) -> str | None:
    key = cache_key("nudge", str(user_id), date.today().isoformat())
    if (cached := cache_get(key)) is not None:
        return cached
    try:
        text = (
            get_ollama()
            .chat(
                [{"role": "system", "content": prompts.NUDGE_SYSTEM}, {"role": "user", "content": context}],
                model=settings.OLLAMA_SECONDARY_MODEL,
                temperature=0.7,
                max_tokens=80,
            )
            .strip()
        )
    except LLMUnavailable:
        return None
    if not text or output_violates_policy(text):
        return None
    cache_set(key, text, ttl=24 * 3600)
    return text


def habits_overview(db: Session, user_id: uuid.UUID, use_ai: bool = False) -> dict[str, Any]:
    current, longest = streaks(db, user_id)
    checklist = _checklist(db, user_id)
    ef_progress = round(sum(i["completed"] for i in checklist) / len(checklist) * 100, 1)
    discipline, sav_streak, recent = _savings(db, user_id)
    this_week = next((r["saved"] for r in recent if r["week_start"] == week_start()), None)
    awareness = scam_awareness(db, user_id)
    recent_high = bool(
        db.scalar(
            select(func.count())
            .select_from(ScamAnalysis)
            .where(
                ScamAnalysis.user_id == user_id,
                ScamAnalysis.risk_level.in_(("high", "critical")),
                ScamAnalysis.created_at >= datetime.now(UTC) - timedelta(days=7),
            )
        )
    )
    nudges = build_nudges(current, ef_progress, this_week, awareness, recent_high)
    if use_ai:
        extra = ai_nudge(
            user_id,
            f"Learning streak {current} days; emergency-fund checklist {ef_progress}% done; "
            f"savings discipline {discipline}%; scam awareness {awareness}%.",
        )
        if extra:
            nudges.insert(0, extra)
    user = db.get(User, user_id)
    lessons_done = sum(
        len(r or []) for r in db.scalars(select(LearningProgress.completed_lessons).where(LearningProgress.user_id == user_id))
    )
    lessons_total = db.scalar(select(func.count()).select_from(Lesson)) or 0
    quiz_total = db.scalar(select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == user_id)) or 0
    quiz_passed = (
        db.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.user_id == user_id, QuizAttempt.score * 100 >= QuizAttempt.total * 60)
        )
        or 0
    )
    weeks_logged = len(recent)
    weeks_saved = sum(1 for r in recent if r["saved"])
    ef = _ef(user) if user else None
    trackers = [
        {
            "key": "emergency_fund",
            "label": "Emergency Fund",
            "value": ef["pct"] if ef else ef_progress,
            "sub": f"₹{ef['saved']:,} of ₹{ef['target']:,}"
            if ef
            else f"{sum(i['completed'] for i in checklist)} of {len(checklist)} steps",
        },
        {"key": "savings", "label": "Savings Consistency", "value": discipline, "sub": f"{weeks_saved} of {weeks_logged} weeks"},
        {
            "key": "learning",
            "label": "Financial Learning",
            "value": round(lessons_done / lessons_total * 100, 1) if lessons_total else 0.0,
            "sub": f"{lessons_done} of {lessons_total} lessons",
        },
        {
            "key": "awareness",
            "label": "Scam Awareness",
            "value": awareness,
            "sub": f"{quiz_passed} of {quiz_total} quizzes passed",
        },
    ]
    from backend.services import safety_service

    drill = safety_service.drill_state(db, user_id)
    shield_items = safety_service.shield(db, user_id)
    challenge = safety_service.weekly_challenge(db, user_id)
    if not drill["done"]:
        nudges.insert(0, "Today's Scam Drill takes 2 minutes. Spot the scams and keep your streak alive.")
    next_step = next((s for s in shield_items if not s["done"]), None)
    if next_step:
        nudges.insert(1, f"Next Safety Shield step: {next_step['title']}.")
    score = (
        safety_service.safety_score(db, user, shield_items, drill, awareness, ef["pct"] if ef else ef_progress) if user else None
    )
    return {
        "safety_score": score,
        "drill": drill,
        "daily": safety_service.daily_goals(db, user_id, drill["done"]),
        "shield": shield_items,
        "weekly_challenge": challenge,
        "trackers": trackers,
        "emergency_fund": ef,
        "learning_streak_days": current,
        "longest_streak_days": longest,
        "scam_awareness_progress": awareness,
        "emergency_fund_checklist": checklist,
        "emergency_fund_progress": ef_progress,
        "savings_discipline": discipline,
        "savings_streak_weeks": sav_streak,
        "recent_savings": recent,
        "nudges": nudges[:5],
    }
