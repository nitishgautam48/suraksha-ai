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
