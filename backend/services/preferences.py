"""Per-user preferences (UI, elder mode, notifications, privacy) stored as JSON on the user row."""

from __future__ import annotations

from typing import Any

from backend.models import User

DEFAULTS: dict[str, Any] = {
    # appearance / accessibility
    "theme": "system",  # system | light | dark | contrast
    "text_scale": 1.0,  # 1.0 - 1.6
    "elder_mode": False,
    "voice_navigation": False,
    "tts_autoplay": False,
    # family protection
    "auto_alert_family": None,  # None = follow elder_mode
    # notifications
    "notify_high_risk": True,
    "notify_learning": True,
    "weekly_report": True,
    "sms_alerts": False,
    "email_alerts": True,
    # privacy
    "auto_delete_scans": False,  # delete scans + uploads after 24 hours
    "share_analytics": False,
}


def get(user: User) -> dict[str, Any]:
    prefs = {**DEFAULTS, **(user.preferences or {})}
    if prefs["auto_alert_family"] is None:
        prefs["auto_alert_family"] = bool(prefs["elder_mode"])
    return prefs


def update(user: User, changes: dict[str, Any]) -> dict[str, Any]:
    merged = {**(user.preferences or {}), **{k: v for k, v in changes.items() if k in DEFAULTS}}
    if changes.get("elder_mode") is True:
        # Elder mode turns on sensible accessibility defaults unless the user chose otherwise.
        merged.setdefault("text_scale", 1.2)
        merged.setdefault("tts_autoplay", True)
    user.preferences = merged  # reassign so SQLAlchemy tracks the JSON change
    return get(user)


def apply_user_type(user: User) -> None:
    """Senior citizens start in elder mode (they can switch it off)."""
    if user.user_type == "senior_citizen" and "elder_mode" not in (user.preferences or {}):
        update(user, {"elder_mode": True})


def is_elder(user: User) -> bool:
    return bool(get(user)["elder_mode"])
