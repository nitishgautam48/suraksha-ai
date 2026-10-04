"""Emergency contacts and the Get Help (alert family) flow."""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import PlainTextResponse

from backend.api.deps import DB, ConsentedUser
from backend.config import settings
from backend.schemas.common import Message
from backend.schemas.family import (
    ContactIn,
    ContactOut,
    ContactUpdate,
    HelpAlertIn,
    HelpAlertOut,
    HelpRequestOut,
    ReadinessUpdate,
)
from backend.security.rate_limit import limiter
from backend.services import family_service

router = APIRouter(tags=["Family Protection"])


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(user: ConsentedUser, db: DB):
    return family_service.list_contacts(db, user.id)


@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def add_contact(request: Request, data: ContactIn, user: ConsentedUser, db: DB):
    """Add a trusted contact (max 5). The first contact becomes primary - the person the app calls."""
    return family_service.add_contact(db, user, data.model_dump())


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: uuid.UUID, data: ContactUpdate, user: ConsentedUser, db: DB):
    return family_service.update_contact(db, user, contact_id, data.model_dump(exclude_unset=True))


@router.delete("/contacts/{contact_id}", response_model=Message)
def delete_contact(contact_id: uuid.UUID, user: ConsentedUser, db: DB):
    family_service.delete_contact(db, user, contact_id)
    return {"detail": "Contact removed"}


@router.post("/help/alert", response_model=HelpAlertOut)
def help_alert(data: HelpAlertIn, user: ConsentedUser, db: DB):
    """The Get Help button: SMS (and email) every trusted contact, then return who to call.
    The device places the call itself using `call.tel` - or the 1930 helpline."""
    loc = data.location.model_dump() if data.location else None
    return family_service.send_help_alert(db, user, data.note, data.analysis_id, loc)


@router.get("/help/history", response_model=list[HelpRequestOut])
def help_history(user: ConsentedUser, db: DB):
    return family_service.history(db, user.id)


# ---- nominee & family-readiness checklist -----------------------------------------------------
@router.get("/family/readiness", tags=["Family Readiness"])
def readiness(user: ConsentedUser, db: DB, language: str | None = None):
    """Checklist per type of holding (bank, FD, demat, mutual funds, insurance, EPF/PPF, NPS, post
    office, locker, property, will): nominee recorded? papers' location noted? family told?
    Awareness and record-keeping only - no account numbers or amounts are ever stored."""
    from backend.api.deps import user_language
    from backend.services import readiness_service

    return readiness_service.overview(db, user.id, user_language(user, language))


@router.put("/family/readiness/{key}", tags=["Family Readiness"])
def update_readiness(key: str, data: ReadinessUpdate, user: ConsentedUser, db: DB):
    from backend.services import readiness_service

    readiness_service.update(db, user.id, key, data.model_dump(exclude_unset=True))
    return readiness_service.overview(db, user.id, user.language or "en")


@router.get("/family/readiness/summary", tags=["Family Readiness"], response_class=PlainTextResponse)
def readiness_summary(user: ConsentedUser, db: DB, language: str | None = None):
    """Printable / shareable summary for the family (statuses and where papers are, nothing else)."""
    from backend.api.deps import user_language
    from backend.services import readiness_service

    return readiness_service.family_summary(db, user.id, user.name, user_language(user, language))
