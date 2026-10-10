from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.common import Disclaimer, LanguageCode, ORMModel, RiskLevelStr, clean


class WarningFlag(BaseModel):
    key: str
    label: str
    category: str
    category_label: str
    reason: str
    evidence: list[str]


class Highlight(BaseModel):
    start: int
    end: int
    text: str
    signal: str
    label: str
    category: str


class LinkInfo(BaseModel):
    url: str
    host: str
    issues: list[str]
    risk: int


class CallAction(BaseModel):
    label: str
    name: str
    tel: str


class SimpleVerdict(BaseModel):
    """One-line, big-print verdict for elder mode and notifications."""

    level: RiskLevelStr
    headline: str
    action: str
    call: CallAction | None = None
    elder_mode: bool = False


class VerifyLink(BaseModel):
    label: str
    tel: str | None = None
    url: str | None = None


class Confidence(BaseModel):
    """How sure the result is, why, and where to verify independently."""

    level: Literal["low", "medium", "high"]
    label: str
    reasons: list[str]
    reason_texts: list[str]
    note: str
    verify: list[VerifyLink]


class PrivacyInfo(BaseModel):
    """Secrets (OTP, card, Aadhaar, ...) masked before analysis; counts per kind."""

    redacted: dict[str, int]
    note: str | None = None


class EngineInfo(BaseModel):
    rule_score: int
    llm_score: int | None
    llm_used: bool
    model: str | None


# ---- Module 1: scam detection -------------------------------------------------------------
class TextScanRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    language: LanguageCode | None = None


class QuickScanRequest(BaseModel):
    text: str = Field(min_length=1, max_length=30000)
    kind: Literal["text", "message", "social"] = "text"
    platform: str = "other"
    language: LanguageCode | None = None


class OCRInfo(BaseModel):
    pages: int
    method: str
    languages: str
    characters: int


class OfficialGuidanceItem(BaseModel):
    id: str
    authority: str
    source: str
    url: str
    point: str


class ScanResponse(Disclaimer):
    simple_verdict: SimpleVerdict | None = None
    confidence: Confidence | None = None
    privacy: PrivacyInfo | None = None
    official_guidance: list[OfficialGuidanceItem] = []
    analysis_id: uuid.UUID
    file_id: uuid.UUID | None = None
    risk_level: RiskLevelStr
    risk_score: int = Field(ge=0, le=100)
    reasons: list[str]
    safe_practices: list[str]
    categories: list[str]
    explanation: str
    warning_flags: list[WarningFlag]
    links: list[LinkInfo]
    extracted_text: str | None = None
    ocr: OCRInfo | None = None
    engine: EngineInfo


class ScanQueued(BaseModel):
    task_id: str
    status: str = "queued"
    file_id: uuid.UUID


# ---- Module 2: WhatsApp message analyzer --------------------------------------------------
class MessageAnalyzeRequest(BaseModel):
    message_text: str = Field(min_length=1, max_length=10000)
    language: LanguageCode | None = None


class MessageAnalyzeResponse(Disclaimer):
    simple_verdict: SimpleVerdict | None = None
    confidence: Confidence | None = None
    privacy: PrivacyInfo | None = None
    official_guidance: list[OfficialGuidanceItem] = []
    analysis_id: uuid.UUID
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevelStr
    warning_flags: list[WarningFlag]
    explanation: str
    reasons: list[str]
    safe_practices: list[str]
    highlights: list[Highlight]
    links: list[LinkInfo]
    phone_numbers: list[str]
    engine: EngineInfo
    extracted_text: str | None = None  # set when the message came from a screenshot


# ---- Module 3: social media analyzer ------------------------------------------------------
Platform = Literal["instagram", "telegram", "youtube", "whatsapp", "facebook", "x", "other"]


class SocialAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=30000, description="Caption, message or transcript")
    platform: Platform = "other"
    language: LanguageCode | None = None


class SocialHighlight(BaseModel):
    start: int
    end: int
    text: str
    tactic: str
    why: str
    source: Literal["rules", "llm"]


class Segment(BaseModel):
    text: str
    risky: bool
    tactics: list[str]


class TacticCount(BaseModel):
    key: str
    label: str
    count: int


class SocialAnalyzeResponse(Disclaimer):
    simple_verdict: SimpleVerdict | None = None
    confidence: Confidence | None = None
    privacy: PrivacyInfo | None = None
    official_guidance: list[OfficialGuidanceItem] = []
    analysis_id: uuid.UUID
    platform: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevelStr
    tactics: list[TacticCount]
    highlights: list[SocialHighlight]
    segments: list[Segment]
    explanation: str
    safe_practices: list[str]
    links: list[LinkInfo]
    engine: EngineInfo


# ---- Link checker (paste a reel / video / channel / post link) -----------------------------
class LinkAnalyzeRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2000, description="Instagram, YouTube, Telegram, X or any web link")
    language: LanguageCode | None = None


class LinkSource(BaseModel):
    title: str = ""
    author: str = ""
    published: str = ""
    kind: str = "page"
    platform_name: str = "Website"
    parts: list[str] = []
    duration_seconds: int | None = None
    transcript_source: str | None = None
    characters: int = 0
    redirects: list[str] = []
    extra: dict[str, str] = {}


class LinkVerdict(BaseModel):
    key: Literal["scam", "suspicious", "no_signs", "unclear"]
    label: str
    icon: str
    headline: str
    summary: str


class LinkReason(BaseModel):
    title: str
    detail: str = ""
    evidence: str = ""
    source: Literal["check", "rules", "ai"]


class LinkClaim(BaseModel):
    claim: str
    assessment: Literal["false", "misleading", "unverifiable", "plausible"]
    why: str = ""


class LinkCheck(BaseModel):
    key: str
    label: str
    status: Literal["fail", "warn", "pass", "info"]
    detail: str = ""
    evidence: str = ""
    link: str | None = None


class LinkAnalyzeResponse(Disclaimer):
    simple_verdict: SimpleVerdict | None = None
    confidence: Confidence | None = None
    privacy: PrivacyInfo | None = None
    official_guidance: list[OfficialGuidanceItem] = []
    analysis_id: uuid.UUID
    url: str
    final_url: str
    platform: str
    source: LinkSource
    fetched: bool
    limitations: list[str]
    verdict: LinkVerdict
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevelStr
    tactics: list[TacticCount]
    highlights: list[SocialHighlight]
    segments: list[Segment]
    reasons: list[LinkReason]
    claims: list[LinkClaim]
    checks: list[LinkCheck]
    genuine_signals: list[str]
    what_to_do: list[str]
    explanation: str
    safe_practices: list[str]
    links: list[LinkInfo]
    engine: EngineInfo


# ---- History ------------------------------------------------------------------------------
class AnalysisSummary(ORMModel):
    id: uuid.UUID
    risk_score: int
    risk_level: str
    source_type: str
    platform: str | None
    categories: list[str]
    input_excerpt: str | None
    created_at: datetime


class AnalysisDetail(AnalysisSummary):
    reasons: list[str]
    safe_practices: list[str]
    explanation: str | None
    llm_used: bool
    file_id: uuid.UUID | None


# ---- Feedback (calibration data) --------------------------------------------------------------
class FeedbackRequest(BaseModel):
    verdict: Literal["scam", "not_scam"]
    comment: clean(500, 0) | None = None
    share_text: bool = Field(False, description="Allow the message excerpt to be used to improve detection")


class FeedbackOut(ORMModel):
    id: uuid.UUID
    analysis_id: uuid.UUID
    verdict: str
    comment: str | None
    share_text: bool
    created_at: datetime


class FeedbackAdminOut(FeedbackOut):
    risk_score: int
    risk_level: str
    source_type: str
    disagrees: bool
