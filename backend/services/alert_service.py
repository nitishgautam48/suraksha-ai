from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.models import SafetyAlert, ScamAnalysis
from backend.models.enums import AlertSeverity, AlertType


def create_alert(
    db: Session,
    user_id: uuid.UUID,
    alert_type: AlertType,
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.INFO,
    analysis_id: uuid.UUID | None = None,
    dedupe_hours: int = 0,
) -> SafetyAlert | None:
    if dedupe_hours:
        since = datetime.now(UTC) - timedelta(hours=dedupe_hours)
        exists = db.scalar(
            select(func.count())
            .select_from(SafetyAlert)
            .where(
                SafetyAlert.user_id == user_id,
                SafetyAlert.alert_type == alert_type.value,
                SafetyAlert.title == title,
                SafetyAlert.created_at >= since,
            )
        )
        if exists:
            return None
    alert = SafetyAlert(
        user_id=user_id,
        alert_type=alert_type.value,
        severity=severity.value,
        title=title[:200],
        message=message,
        analysis_id=analysis_id,
    )
    db.add(alert)
    return alert


def alerts_for_analysis(db: Session, analysis: ScamAnalysis, links: list[dict]) -> None:
    if analysis.risk_level in ("high", "critical"):
        create_alert(
            db,
            analysis.user_id,
            AlertType.HIGH_RISK_SCAN,
            f"{'Dangerous' if analysis.risk_level == 'critical' else 'High-risk'} content detected ({analysis.risk_score}/100)",
            "Do not send money, click links or share OTP/PIN. "
            "If you have already paid, call the Cyber Crime Helpline 1930 immediately.",
            AlertSeverity.CRITICAL if analysis.risk_level == "critical" else AlertSeverity.WARNING,
            analysis.id,
        )
    risky_hosts = [link["host"] for link in links if link.get("risk", 0) >= 50]
    if risky_hosts:
        create_alert(
            db,
            analysis.user_id,
            AlertType.PHISHING_LINK,
            "Suspicious link detected",
            f"The link(s) {', '.join(risky_hosts[:3])} show phishing signs. Do not open them or enter any details.",
            AlertSeverity.WARNING,
            analysis.id,
        )


def list_alerts(db: Session, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int):
    q = select(SafetyAlert).where(SafetyAlert.user_id == user_id)
    if unread_only:
        q = q.where(SafetyAlert.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    unread = db.scalar(
        select(func.count()).select_from(SafetyAlert).where(SafetyAlert.user_id == user_id, SafetyAlert.is_read.is_(False))
    )
    items = db.scalars(q.order_by(SafetyAlert.created_at.desc()).limit(limit).offset(offset)).all()
    return total or 0, unread or 0, items


def mark_read(db: Session, user_id: uuid.UUID, alert_id: uuid.UUID | None = None) -> int:
    stmt = update(SafetyAlert).where(SafetyAlert.user_id == user_id, SafetyAlert.is_read.is_(False))
    if alert_id:
        stmt = stmt.where(SafetyAlert.id == alert_id)
    res = db.execute(stmt.values(is_read=True))
    db.commit()
    return res.rowcount or 0
