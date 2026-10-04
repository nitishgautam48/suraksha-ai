from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from backend.schemas.analysis import AnalysisSummary
from backend.schemas.common import ORMModel


class AlertOut(ORMModel):
    id: uuid.UUID
    alert_type: str
    severity: str
    title: str
    message: str
    is_read: bool
    analysis_id: uuid.UUID | None
    created_at: datetime


class AlertList(BaseModel):
    unread_count: int
    total: int
    items: list[AlertOut]


class SafetyScoreBreakdown(BaseModel):
    learning: float
    quiz_performance: float
    habits: float
    vigilance: float


class SafetyScore(BaseModel):
    score: int
    label: str
    breakdown: SafetyScoreBreakdown


class ScanHistory(BaseModel):
    total_scans: int
    by_level: dict[str, int]
    threats_caught: int
    recent: list[AnalysisSummary]


class TrendPoint(BaseModel):
    week_start: date
    awareness_score: float
    scans: int
    lessons: int
    quizzes: int


class LearningSummary(BaseModel):
    overall_completion: float
    learning_streak_days: int
    courses_completed: int
    courses_total: int


class DashboardLevel(BaseModel):
    xp: int
    level: int
    label: str
    xp_to_next: int
    progress_pct: float


class DashboardActivity(BaseModel):
    icon: str
    tone: str
    title: str
    meta: str
    time: datetime


class DashboardOut(BaseModel):
    user_name: str
    level: DashboardLevel
    recent_activity: list[DashboardActivity]
    safety_score: SafetyScore
    scam_detection_history: ScanHistory
    learning_progress: LearningSummary
    recent_alerts: list[AlertOut]
    awareness_trend: list[TrendPoint]
    nudge: str | None
