from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from backend.schemas.common import LanguageCode, ORMModel, clean


class ContactIn(BaseModel):
    name: clean(120)
    relationship: clean(40) = "family"
    phone: str = Field(min_length=10, max_length=20)
    email: EmailStr | None = None
    language: LanguageCode | None = None
    is_primary: bool = False
    notify_on_high_risk: bool = True
    notify_contact: bool = Field(True, description="Send the contact a courtesy SMS that they were added")


class ContactUpdate(BaseModel):
    name: clean(120) | None = None
    relationship: clean(40) | None = None
    phone: str | None = Field(None, min_length=10, max_length=20)
    email: EmailStr | None = None
    language: LanguageCode | None = None
    is_primary: bool | None = None
    notify_on_high_risk: bool | None = None


class ContactOut(ORMModel):
    id: uuid.UUID
    name: str
    relationship: str
    phone: str
    email: str | None
    language: str
    is_primary: bool
    notify_on_high_risk: bool
    created_at: datetime


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class HelpAlertIn(BaseModel):
    note: clean(200, 0) | None = Field(None, description="Optional short message for the family")
    analysis_id: uuid.UUID | None = None
    location: Location | None = None


class CallTarget(BaseModel):
    name: str
    relationship: str
    phone: str
    tel: str


class Helpline(BaseModel):
    name: str
    number: str
    tel: str


class HelpAlertOut(BaseModel):
    status: str
    notified: list[dict]
    call: CallTarget
    helplines: list[Helpline]


class HelpRequestOut(ORMModel):
    id: uuid.UUID
    reason: str
    message: str | None
    analysis_id: uuid.UUID | None
    results: list
    created_at: datetime


class ReadinessUpdate(BaseModel):
    """Statuses only. Never send account numbers, amounts or passwords (they are masked if you do)."""

    applicable: bool | None = None
    nominee: Literal["yes", "no", "not_sure"] | None = None
    documents_location: clean(120) | None = Field(None, description="e.g. 'steel almirah, blue file'")
    family_informed: bool | None = None
