"""Module 4: Financial Habit Coach."""

from fastapi import APIRouter

from backend.api.deps import DB, CurrentUser
from backend.schemas.common import Message
from backend.schemas.habits import (
    ChecklistUpdate,
    DrillAnswerOut,
    DrillAnswerRequest,
    DrillState,
    EmergencyFund,
    EmergencyFundUpdate,
    HabitsOut,
    SavingsCheckinRequest,
)
from backend.services import habit_service, safety_service

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


@router.get("/drill", response_model=DrillState)
def drill(user: CurrentUser, db: DB):
    """Today's Scam Drill: 3 real-style messages (at least one scam and one genuine)."""
    return safety_service.drill_state(db, user.id)


@router.post("/drill/answer", response_model=DrillAnswerOut)
def drill_answer(data: DrillAnswerRequest, user: CurrentUser, db: DB):
    """Answer 'scam' or 'genuine' for one of today's drill messages; returns the explanation and XP."""
    return safety_service.answer_drill(db, user.id, data.item_id, data.answer)


@router.put("/shield/{key}", response_model=Message)
def shield_step(key: str, data: ChecklistUpdate, user: CurrentUser, db: DB):
    """Mark a Safety Shield protection step (WhatsApp two-step, UPI limit, Aadhaar lock...) done or not."""
    safety_service.set_shield(db, user.id, key, data.completed)
    return {"detail": "Safety Shield updated"}


@router.post("/weekly-challenge", response_model=Message)
def weekly_challenge(user: CurrentUser, db: DB):
    """Mark this week's safety challenge as done (+40 XP, once per week)."""
    xp = safety_service.complete_weekly_challenge(db, user.id)
    return {"detail": f"Challenge complete! +{xp} XP" if xp else "Already completed this week"}
