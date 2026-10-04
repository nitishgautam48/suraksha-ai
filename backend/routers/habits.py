"""Module 4: Financial Habit Coach."""

from fastapi import APIRouter

from backend.api.deps import DB, CurrentUser
from backend.schemas.common import Message
from backend.schemas.habits import ChecklistUpdate, EmergencyFund, EmergencyFundUpdate, HabitsOut, SavingsCheckinRequest
from backend.services import habit_service

router = APIRouter(prefix="/habits", tags=["Financial Habit Coach"])


@router.get("", response_model=HabitsOut)
def overview(user: CurrentUser, db: DB, ai_nudge: bool = False):
    """Learning streak, scam-awareness progress, emergency-fund checklist, savings discipline and
    behavioural nudges. Never includes investment recommendations."""
    return habit_service.habits_overview(db, user.id, use_ai=ai_nudge)


@router.put("/checklist/{item_key}", response_model=Message)
def update_checklist(item_key: str, data: ChecklistUpdate, user: CurrentUser, db: DB):
    habit_service.set_checklist_item(db, user.id, item_key, data.completed)
    return {"detail": "Checklist updated"}


@router.put("/emergency-fund", response_model=EmergencyFund | None)
def emergency_fund(data: EmergencyFundUpdate, user: CurrentUser, db: DB):
    """Track your own emergency-fund goal (e.g. ₹31,000 of ₹50,000). Amounts stay private to you."""
    return habit_service.set_emergency_fund(db, user.id, data.target, data.saved)


@router.post("/savings-checkin", response_model=Message)
def savings_checkin(data: SavingsCheckinRequest, user: CurrentUser, db: DB):
    """Weekly yes/no savings check-in (no amounts or products are recorded)."""
    habit_service.savings_checkin(db, user.id, data.saved, data.note)
    return {"detail": "Check-in recorded" + (" - well done!" if data.saved else ". Next week is a fresh start.")}
