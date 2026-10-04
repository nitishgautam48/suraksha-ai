"""String enums shared by models and schemas."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    EDUCATOR = "educator"  # may author/generate learning content
    ADMIN = "admin"


class Language(StrEnum):
    EN = "en"
    HI = "hi"
    GU = "gu"
    MR = "mr"
    TA = "ta"
    BN = "bn"
    TE = "te"
    KN = "kn"
    ML = "ml"
    PA = "pa"
    OR = "or"
    AS = "as"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(StrEnum):
    TEXT = "text"
    MESSAGE = "message"
    SOCIAL = "social"
    IMAGE = "image"
    PDF = "pdf"
    VOICE = "voice"


class AlertType(StrEnum):
    HIGH_RISK_SCAN = "high_risk_scan"
    PHISHING_LINK = "phishing_link"
    LEARNING_NUDGE = "learning_nudge"
    HABIT_NUDGE = "habit_nudge"
    FAMILY_ALERT = "family_alert"
    ACHIEVEMENT = "achievement"
    TRENDING = "trending"
    SECURITY = "security"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
