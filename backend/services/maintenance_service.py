"""Scheduled jobs: 24-hour scan auto-delete, weekly safety reports, learning nudges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import ScamAnalysis, UploadedFile, User
from backend.models.enums import AlertSeverity, AlertType
from backend.services import dashboard_service, email_service, messages, preferences, sms_service
from backend.services.alert_service import create_alert
from backend.services.habit_service import habits_overview
from backend.utils.logging import get_logger

log = get_logger(__name__)
RETENTION = timedelta(hours=24)


def _active_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active.is_(True))).all())


def _unlink(f: UploadedFile) -> None:
    path = Path(f.file_path)
    if path.resolve().is_relative_to(settings.UPLOAD_DIR.resolve()):
        path.unlink(missing_ok=True)


def purge_expired_scans(db: Session) -> int:
    """Privacy retention, run hourly:

    * every user: upload bytes older than 24 hours are deleted (normally they are already gone,
      removed straight after text extraction) and analyses older than ANALYSIS_RETENTION_DAYS;
    * users who enabled 'Delete scans after 24 hours': analyses and upload records after 24 hours.
    """
    now = datetime.now(UTC)
    cutoff = now - RETENTION
    removed = 0
    for f in db.scalars(select(UploadedFile).where(UploadedFile.deleted_at.is_(None), UploadedFile.created_at < cutoff)):
        _unlink(f)
        f.deleted_at = now
    if settings.ANALYSIS_RETENTION_DAYS > 0:
        old = now - timedelta(days=settings.ANALYSIS_RETENTION_DAYS)
        removed += db.execute(delete(ScamAnalysis).where(ScamAnalysis.created_at < old)).rowcount or 0
    for user in _active_users(db):
        if not preferences.get(user)["auto_delete_scans"]:
            continue
        files = db.scalars(select(UploadedFile).where(UploadedFile.user_id == user.id, UploadedFile.created_at < cutoff)).all()
        for f in files:
            _unlink(f)
        res = db.execute(delete(ScamAnalysis).where(ScamAnalysis.user_id == user.id, ScamAnalysis.created_at < cutoff))
        db.execute(delete(UploadedFile).where(UploadedFile.user_id == user.id, UploadedFile.created_at < cutoff))
        removed += res.rowcount or 0
    db.commit()
    return removed


def send_weekly_reports(db: Session) -> int:
    sent = 0
    for user in _active_users(db):
        prefs = preferences.get(user)
        if not prefs["weekly_report"]:
            continue
        d = dashboard_service.dashboard(db, user)
        history = d["scam_detection_history"]
        text = messages.text(
            "weekly_report",
            user.language,
            name=user.name,
            score=d["safety_score"]["score"],
            scans=history["total_scans"],
            threats=history["threats_caught"],
            streak=d["learning_progress"]["learning_streak_days"],
            nudge=d["nudge"] or "",
        )
        if user.email and prefs["email_alerts"]:
            email_service.send_email(user.email, "Your Suraksha AI weekly safety report", text)
        elif user.phone and prefs["sms_alerts"]:
            sms_service.send_sms(user.phone, text, "weekly_report")
        else:
            continue
        sent += 1
    return sent


def send_daily_nudges(db: Session) -> int:
    sent = 0
    for user in _active_users(db):
        if not preferences.get(user)["notify_learning"]:
            continue
        nudges = habits_overview(db, user.id)["nudges"]
        if nudges and create_alert(
            db, user.id, AlertType.HABIT_NUDGE, "Your daily safety nudge", nudges[0], AlertSeverity.INFO, dedupe_hours=20
        ):
            sent += 1
    db.commit()
    return sent
