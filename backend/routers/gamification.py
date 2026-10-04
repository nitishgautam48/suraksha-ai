"""XP, levels, badges and activity views."""

from fastapi import APIRouter, Query

from backend.api.deps import DB, CurrentUser
from backend.schemas.gamification import ActivityItem, ClaimOut, GamificationOut, HeatmapOut
from backend.services import gamification_service

router = APIRouter(tags=["Progress & Rewards"])


@router.get("/gamification", response_model=GamificationOut)
def overview(user: CurrentUser, db: DB):
    """XP, level (e.g. "Level 6 · Guardian"), progress to the next level, badges and recent XP."""
    return gamification_service.overview(db, user)


@router.post("/gamification/achievements/{key}/claim", response_model=ClaimOut)
def claim(key: str, user: CurrentUser, db: DB):
    """Claim an unlocked badge for its XP bonus."""
    return gamification_service.claim(db, user.id, key)


@router.get("/activity/heatmap", response_model=HeatmapOut)
def heatmap(user: CurrentUser, db: DB, weeks: int = Query(14, ge=1, le=52)):
    """Daily activity for the habit heatmap (levels 0-4)."""
    return gamification_service.heatmap(db, user.id, weeks)


@router.get("/activity/recent", response_model=list[ActivityItem])
def recent(user: CurrentUser, db: DB, limit: int = Query(10, ge=1, le=50)):
    """Recent activity feed: scans, lessons, badges, habits."""
    return gamification_service.recent_activity(db, user.id, limit)
