from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class LevelInfo(BaseModel):
    xp: int
    level: int
    level_name: str
    label: str
    current_level_xp: int
    next_level_xp: int | None
    xp_to_next: int
    progress_pct: float


class AchievementOut(BaseModel):
    key: str
    title: str
    description: str
    icon: str
    tone: str
    state: str  # locked | claim | earned
    progress: int
    target: int
    bonus_xp: int
    unlocked_at: datetime | None
    claimed_at: datetime | None


class XPItem(BaseModel):
    action: str
    title: str
    xp: int
    created_at: datetime


class GamificationOut(LevelInfo):
    achievements: list[AchievementOut]
    recent_xp: list[XPItem]


class ClaimOut(LevelInfo):
    key: str
    xp_awarded: int


class HeatDay(BaseModel):
    date: date
    count: int
    level: int
    future: bool


class HeatmapOut(BaseModel):
    weeks: int
    start: date
    active_days: int
    days: list[HeatDay]


class ActivityItem(BaseModel):
    icon: str
    tone: str
    title: str
    meta: str
    time: datetime
