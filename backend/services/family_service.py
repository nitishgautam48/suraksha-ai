"""Module: emergency contacts and family alerts ("Get Help" button + automatic high-risk alerts)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.ai.risk_engine import category_label
from backend.models import EmergencyContact, HelpRequest, ScamAnalysis, User
from backend.models.enums import AlertSeverity, AlertType
from backend.services import email_service, messages, preferences, sms_service
from backend.services.alert_service import create_alert
from backend.services.audit_service import record_audit
from backend.services.gamification_service import award
from backend.utils.cache import get_redis
from backend.utils.logging import get_logger
from backend.utils.phone import InvalidPhone, mask_phone, normalize_phone
from backend.utils.redact import redact

log = get_logger(__name__)
MAX_CONTACTS = 5
HELP_LIMIT, HELP_WINDOW = 3, 600  # 3 help alerts per 10 minutes
AUTO_ALERT_COOLDOWN = 6 * 3600
HELPLINES = [
    {"name": "National Cyber Crime Helpline", "number": "1930", "tel": "tel:1930"},
    {"name": "Police / Emergency", "number": "112", "tel": "tel:112"},
]


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhone as exc:
        raise HTTPException(422, str(exc)) from exc


def list_contacts(db: Session, user_id: uuid.UUID) -> list[EmergencyContact]:
    return list(
        db.scalars(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
            .order_by(EmergencyContact.is_primary.desc(), EmergencyContact.created_at)
        ).all()
    )


def _get(db: Session, user_id: uuid.UUID, contact_id: uuid.UUID) -> EmergencyContact:
    c = db.get(EmergencyContact, contact_id)
    if c is None or c.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    return c


def _make_primary(db: Session, contact: EmergencyContact) -> None:
    for other in list_contacts(db, contact.user_id):
        other.is_primary = other.id == contact.id


def add_contact(db: Session, user: User, data: dict[str, Any]) -> EmergencyContact:
    existing = list_contacts(db, user.id)
    if len(existing) >= MAX_CONTACTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You can add up to {MAX_CONTACTS} trusted contacts")
    phone = _phone(data["phone"])
    if user.phone and phone == user.phone:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A trusted contact must be someone else's number")
    if any(c.phone == phone for c in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "This number is already a trusted contact")
    contact = EmergencyContact(
        user_id=user.id,
        name=data["name"],
        relationship=data.get("relationship") or "family",
        phone=phone,
        email=(data.get("email") or None),
        language=data.get("language") or user.language,
        notify_on_high_risk=data.get("notify_on_high_risk", True),
        is_primary=False,
    )
    db.add(contact)
    db.flush()
    if not existing or data.get("is_primary"):
        _make_primary(db, contact)
    award(db, user.id, "trusted_contact")
    db.commit()
    if data.get("notify_contact", True):
        sms_service.send_sms(phone, messages.text("contact_added", contact.language, name=user.name), "contact_added")
        contact.notified_added_at = func.now()
        db.commit()
    db.refresh(contact)
    record_audit("family.contact_added", user.id, details={"phone": mask_phone(phone)})
    return contact


def update_contact(db: Session, user: User, contact_id: uuid.UUID, changes: dict[str, Any]) -> EmergencyContact:
    c = _get(db, user.id, contact_id)
    if "phone" in changes and changes["phone"]:
        changes["phone"] = _phone(changes["phone"])
    for key in ("name", "relationship", "phone", "email", "language", "notify_on_high_risk"):
        if key in changes and changes[key] is not None:
            setattr(c, key, changes[key])
    if changes.get("is_primary"):
        _make_primary(db, c)
    db.commit()
    db.refresh(c)
    return c


def delete_contact(db: Session, user: User, contact_id: uuid.UUID) -> None:
    c = _get(db, user.id, contact_id)
    was_primary = c.is_primary
    db.delete(c)
    db.flush()
    rest = list_contacts(db, user.id)
    if was_primary and rest:
        _make_primary(db, rest[0])
    db.commit()


def _rate_ok(key: str, limit: int, window: int) -> bool:
    try:
        r = get_redis()
        n = r.incr(key)
        if n == 1:
            r.expire(key, window)
        return n <= limit
    except Exception:
        return True  # never block a real emergency because Redis is down


def _notify(contact: EmergencyContact, text: str, purpose: str, subject: str) -> dict[str, Any]:
    channels = {}
    sms_service.send_sms(contact.phone, text, purpose)
    channels["sms"] = "queued"
    if contact.email:
        email_service.send_email(contact.email, subject, text)
        channels["email"] = "queued"
    return {
        "contact_id": str(contact.id),
        "name": contact.name,
        "relationship": contact.relationship,
        "phone": mask_phone(contact.phone),
        "channels": channels,
    }


def send_help_alert(
    db: Session, user: User, note: str | None, analysis_id: uuid.UUID | None, location: dict | None
) -> dict[str, Any]:
    contacts = list_contacts(db, user.id)
    if not contacts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a trusted contact first (POST /contacts)")
    if analysis_id:
        a = db.get(ScamAnalysis, analysis_id)
        if a is None or a.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    if not _rate_ok(f"suraksha:help:{user.id}", HELP_LIMIT, HELP_WINDOW):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Your family was just alerted. Please call them or 1930.")
    note = redact(note)[0] if note else note  # an OTP or card number never goes out by SMS or into the log
    loc = f" Location: https://maps.google.com/?q={location['lat']:.5f},{location['lon']:.5f}" if location else ""
    results = []
    for c in contacts:
        text = messages.text(
            "help_alert",
            c.language,
            name=user.name,
            phone=user.phone or "their phone",
            note=f' "{note}"' if note else "",
            location=loc,
        )
        results.append(_notify(c, text, "help_alert", f"HELP: {user.name} needs you now"))
    db.add(HelpRequest(user_id=user.id, reason="help_button", message=note, analysis_id=analysis_id, results=results))
    names = ", ".join(c.name for c in contacts)
    create_alert(
        db,
        user.id,
        AlertType.FAMILY_ALERT,
        "Your family has been alerted",
        f"We sent an alert to {names}. If you lost money, call 1930 now.",
        AlertSeverity.WARNING,
        analysis_id,
    )
    db.commit()
    record_audit("family.help_alert", user.id, details={"contacts": len(contacts)})
    primary = contacts[0]
    return {
        "status": "sent",
        "notified": results,
        "call": {
            "name": primary.name,
            "relationship": primary.relationship,
            "phone": primary.phone,
            "tel": f"tel:{primary.phone}",
        },
        "helplines": HELPLINES,
    }


def auto_alert_for_analysis(db: Session, analysis: ScamAnalysis) -> bool:
    """Alert opted-in family when a dangerous scam reaches the user (at most once per 6 hours)."""
    user = db.get(User, analysis.user_id)
    if user is None:
        return False
    prefs = preferences.get(user)
    trigger = analysis.risk_level == "critical" or (analysis.risk_level == "high" and prefs["elder_mode"])
    if not (prefs["auto_alert_family"] and trigger):
        return False
    contacts = [c for c in list_contacts(db, user.id) if c.notify_on_high_risk]
    if not contacts:
        return False
    try:
        if not get_redis().set(f"suraksha:auto-alert:{user.id}", "1", nx=True, ex=AUTO_ALERT_COOLDOWN):
            return False
    except Exception as exc:  # Redis down: still alert (better a duplicate than a missed warning)
        log.warning("auto-alert throttle unavailable: %s", exc)
    category = category_label(analysis.categories[0]) if analysis.categories else "suspicious message"
    results = [
        _notify(
            c,
            messages.text("auto_alert", c.language, name=user.name, phone=user.phone or "their phone", category=category),
            "auto_alert",
            f"Suraksha AI: please check on {user.name}",
        )
        for c in contacts
    ]
    db.add(HelpRequest(user_id=user.id, reason="auto_high_risk", analysis_id=analysis.id, results=results))
    create_alert(
        db,
        user.id,
        AlertType.FAMILY_ALERT,
        "We let your family know",
        f"Because this message looked dangerous, we alerted {', '.join(c.name for c in contacts)}.",
        AlertSeverity.INFO,
        analysis.id,
    )
    return True


def history(db: Session, user_id: uuid.UUID, limit: int = 20) -> list[HelpRequest]:
    return list(
        db.scalars(
            select(HelpRequest).where(HelpRequest.user_id == user_id).order_by(HelpRequest.created_at.desc()).limit(limit)
        ).all()
    )
