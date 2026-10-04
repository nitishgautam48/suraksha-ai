from __future__ import annotations

from datetime import date

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
