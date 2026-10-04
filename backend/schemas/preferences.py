from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    theme: Literal["system", "light", "dark", "contrast"] = "system"
    text_scale: float = Field(1.0, ge=1.0, le=1.6)
    elder_mode: bool = False
    voice_navigation: bool = False
    tts_autoplay: bool = False
    auto_alert_family: bool = False
    notify_high_risk: bool = True
    notify_learning: bool = True
    weekly_report: bool = True
    sms_alerts: bool = False
    email_alerts: bool = True
    auto_delete_scans: bool = False
    share_analytics: bool = False


class PreferencesUpdate(BaseModel):
    theme: Literal["system", "light", "dark", "contrast"] | None = None
    text_scale: float | None = Field(None, ge=1.0, le=1.6)
    elder_mode: bool | None = None
    voice_navigation: bool | None = None
    tts_autoplay: bool | None = None
    auto_alert_family: bool | None = Field(None, description="SMS trusted contacts when a dangerous scam is found")
    notify_high_risk: bool | None = None
    notify_learning: bool | None = None
    weekly_report: bool | None = None
    sms_alerts: bool | None = None
    email_alerts: bool | None = None
    auto_delete_scans: bool | None = Field(None, description="Delete scans and uploaded files after 24 hours")
    share_analytics: bool | None = None
