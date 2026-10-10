from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.common import clean


class ChecklistItem(BaseModel):
    key: str
    title: str
    description: str
    completed: bool


class ChecklistUpdate(BaseModel):
    completed: bool = True


class SavingsCheckinRequest(BaseModel):
    saved: bool = Field(description="Did you set aside savings this week? No amounts are recorded.")
    note: clean(300, 0) | None = None


class SavingsWeek(BaseModel):
    week_start: date
    saved: bool


class Tracker(BaseModel):
    key: str
    label: str
    value: float
    sub: str


class EmergencyFund(BaseModel):
    target: int
    saved: int
    pct: float


class EmergencyFundUpdate(BaseModel):
    target: int | None = Field(None, ge=0, le=100_000_000, description="Your goal in rupees")
    saved: int | None = Field(None, ge=0, le=100_000_000, description="Amount you have set aside so far")


class DrillMark(BaseModel):
    start: int
    end: int


class DrillItem(BaseModel):
    id: str
    text: str
    answered: bool
    correct: bool | None = None
    label: Literal["scam", "genuine"] | None = None
    tip: str | None = None
    signals: list[str] = []
    marks: list[DrillMark] = []


class DrillState(BaseModel):
    date: date
    items: list[DrillItem]
    done: bool
    correct_today: int
    accuracy_30d: float | None
    answered_30d: int
    streak_days: int
    best_streak_days: int


class DrillAnswerRequest(BaseModel):
    item_id: str = Field(max_length=10)
    answer: Literal["scam", "genuine"]


class DrillAnswerOut(BaseModel):
    id: str
    correct: bool
    label: Literal["scam", "genuine"]
    xp_awarded: int
    done: bool
    remaining: int
    tip: str
    signals: list[str]
    marks: list[DrillMark]


class ShieldItem(BaseModel):
    key: str
    icon: str
    title: str
    why: str
    how: str
    link: str | None
    auto: bool
    done: bool
    done_at: datetime | None = None


class DailyGoal(BaseModel):
    key: str
    icon: str
    title: str
    detail: str
    page: str
    done: bool
    week: list[bool]


class DailyGoals(BaseModel):
    goals: list[DailyGoal]
    days: list[str]
    completed: int
    total: int


class WeeklyChallenge(BaseModel):
    key: str
    icon: str
    title: str
    detail: str
    week: str
    done: bool
    xp: int
    days_left: int


class ScorePart(BaseModel):
    key: str
    label: str
    pct: int
    weight: int


class ScoreBooster(BaseModel):
    key: str
    icon: str
    title: str
    page: str
    points: int


class ScorePoint(BaseModel):
    week: str
    score: int


class SafetyScore(BaseModel):
    score: int
    min: int
    max: int
    band: str
    tone: str
    pct: float
    change: int | None
    history: list[ScorePoint]
    parts: list[ScorePart]
    boosters: list[ScoreBooster]


class HabitsOut(BaseModel):
    trackers: list[Tracker]
    emergency_fund: EmergencyFund | None
    learning_streak_days: int
    longest_streak_days: int
    scam_awareness_progress: float
    emergency_fund_checklist: list[ChecklistItem]
    emergency_fund_progress: float
    savings_discipline: float
    savings_streak_weeks: int
    recent_savings: list[SavingsWeek]
    nudges: list[str]
    safety_score: SafetyScore | None = None
    drill: DrillState | None = None
    daily: DailyGoals | None = None
    shield: list[ShieldItem] = []
    weekly_challenge: WeeklyChallenge | None = None
