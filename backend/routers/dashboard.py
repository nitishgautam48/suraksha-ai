import uuid

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.deps import DB, CurrentUser
from backend.schemas.common import Message
from backend.schemas.dashboard import AlertList, DashboardOut
from backend.schemas.learning import ProgressOut
from backend.services import alert_service, dashboard_service, learning_service

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser, db: DB):
    """Safety score, scam-detection history, learning progress, recent alerts and awareness trend."""
    return dashboard_service.dashboard(db, user)


@router.get("/progress", response_model=ProgressOut)
def progress(user: CurrentUser, db: DB):
    """Learning progress across all courses, streaks and quiz performance."""
    return learning_service.progress_overview(db, user.id)


@router.get("/alerts", response_model=AlertList)
def alerts(
    user: CurrentUser, db: DB, unread_only: bool = False, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
):
    total, unread, items = alert_service.list_alerts(db, user.id, unread_only, limit, offset)
    return {"total": total, "unread_count": unread, "items": items}


@router.post("/alerts/{alert_id}/read", response_model=Message)
def mark_alert_read(alert_id: uuid.UUID, user: CurrentUser, db: DB):
    if not alert_service.mark_read(db, user.id, alert_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found or already read")
    return {"detail": "Alert marked as read"}


@router.post("/alerts/read-all", response_model=Message)
def mark_all_read(user: CurrentUser, db: DB):
    n = alert_service.mark_read(db, user.id)
    return {"detail": f"{n} alert(s) marked as read"}
