"""Dashboard metrics: safety score, scan history, learning progress, alerts, awareness trend."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Lesson, QuizAttempt, SafetyAlert, ScamAnalysis, User, UserActivity
from backend.services import habit_service, learning_service


def _label(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Fair"
    return "Needs attention"


def _vigilance(db: Session, user_id: uuid.UUID) -> float:
    since = datetime.now(UTC) - timedelta(days=30)
    scans = (
        db.scalar(
            select(func.count())
            .select_from(ScamAnalysis)
            .where(ScamAnalysis.user_id == user_id, ScamAnalysis.created_at >= since)
        )
        or 0
    )
    total_alerts = db.scalar(select(func.count()).select_from(SafetyAlert).where(SafetyAlert.user_id == user_id)) or 0
    read_alerts = (
        db.scalar(
            select(func.count()).select_from(SafetyAlert).where(SafetyAlert.user_id == user_id, SafetyAlert.is_read.is_(True))
        )
        or 0
    )
    read_ratio = (read_alerts / total_alerts) if total_alerts else 1.0
    return round(0.6 * min(100.0, scans * 20.0) + 0.4 * read_ratio * 100, 1)


def safety_score(db: Session, user_id: uuid.UUID, progress: dict[str, Any], habits: dict[str, Any]) -> dict[str, Any]:
    learning = progress["overall_completion"]
    quiz = progress["average_quiz_score"] or 0.0
    habit_part = round((habits["emergency_fund_progress"] + habits["savings_discipline"]) / 2, 1)
    vigilance = _vigilance(db, user_id)
    score = round(0.30 * learning + 0.25 * quiz + 0.20 * habit_part + 0.25 * vigilance)
    return {
        "score": score,
        "label": _label(score),
        "breakdown": {"learning": learning, "quiz_performance": round(quiz, 1), "habits": habit_part, "vigilance": vigilance},
    }


def scan_history(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    rows = db.execute(
        select(ScamAnalysis.risk_level, func.count()).where(ScamAnalysis.user_id == user_id).group_by(ScamAnalysis.risk_level)
    ).all()
    by_level = {lvl: 0 for lvl in ("low", "medium", "high", "critical")} | {lvl: n for lvl, n in rows}
    recent = db.scalars(
        select(ScamAnalysis).where(ScamAnalysis.user_id == user_id).order_by(ScamAnalysis.created_at.desc()).limit(10)
    ).all()
    return {
        "total_scans": sum(by_level.values()),
        "by_level": by_level,
        "threats_caught": by_level["high"] + by_level["critical"],
        "recent": recent,
    }


def awareness_trend(db: Session, user_id: uuid.UUID, weeks: int = 8) -> list[dict[str, Any]]:
    total_lessons = db.scalar(select(func.count()).select_from(Lesson)) or 1
    start = habit_service.week_start() - timedelta(weeks=weeks - 1)
    activity = db.execute(
        select(UserActivity.activity_date, UserActivity.kind, UserActivity.count).where(UserActivity.user_id == user_id)
    ).all()
    attempts = db.execute(
        select(QuizAttempt.created_at, QuizAttempt.score, QuizAttempt.total).where(QuizAttempt.user_id == user_id)
    ).all()
    points = []
    for i in range(weeks):
        ws = start + timedelta(weeks=i)
        we = ws + timedelta(days=6)
        we_dt = datetime.combine(we, time.max, tzinfo=UTC)
        in_week = [a for a in activity if ws <= a.activity_date <= we]
        cum_lessons = sum(a.count for a in activity if a.kind == "lesson" and a.activity_date <= we)
        prior = [a.score / a.total * 100 for a in attempts if _aware(a.created_at) <= we_dt and a.total]
        lesson_pct = min(cum_lessons / total_lessons * 100, 100.0)
        quiz_pct = sum(prior) / len(prior) if prior else 0.0
        points.append(
            {
                "week_start": ws,
                "awareness_score": round(0.6 * lesson_pct + 0.4 * quiz_pct, 1),
                "scans": sum(a.count for a in in_week if a.kind == "scan"),
                "lessons": sum(a.count for a in in_week if a.kind == "lesson"),
                "quizzes": sum(a.count for a in in_week if a.kind == "quiz"),
            }
        )
    return points


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def dashboard(db: Session, user: User) -> dict[str, Any]:
    progress = learning_service.progress_overview(db, user.id)
    habits = habit_service.habits_overview(db, user.id)
    alerts = db.scalars(
        select(SafetyAlert).where(SafetyAlert.user_id == user.id).order_by(SafetyAlert.created_at.desc()).limit(5)
    ).all()
    from backend.services import gamification_service

    return {
        "user_name": user.name,
        "level": gamification_service.level_for(user.xp or 0),
        "recent_activity": gamification_service.recent_activity(db, user.id, 6),
        "safety_score": safety_score(db, user.id, progress, habits),
        "scam_detection_history": scan_history(db, user.id),
        "learning_progress": {
            "overall_completion": progress["overall_completion"],
            "learning_streak_days": progress["learning_streak_days"],
            "courses_completed": sum(1 for c in progress["courses"] if c["completion"] >= 100),
            "courses_total": len(progress["courses"]),
        },
        "recent_alerts": alerts,
        "awareness_trend": awareness_trend(db, user.id),
        "nudge": habits["nudges"][0] if habits["nudges"] else None,
    }
