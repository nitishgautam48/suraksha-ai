from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.schemas.common import LanguageCode, ORMModel, clean
from backend.security.passwords import password_problems
from backend.utils.india import IndianState


class UserOut(ORMModel):
    id: uuid.UUID
    name: str
    email: EmailStr | None
    phone: str | None
    phone_verified: bool
    city: str | None
    state: str | None = None
    user_type: str | None
    language: str
    role: str
    auth_provider: str
    email_verified: bool
    consent_version: str | None = None
    created_at: datetime


def _check_strength(v: str) -> str:
    if problems := password_problems(v):
        raise ValueError("Password " + ", ".join(problems))
    return v


class RegisterRequest(BaseModel):
    name: clean(120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    language: LanguageCode = "en"
    consent: bool = Field(default=False, description="User accepted the privacy notice shown by GET /privacy")

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return _check_strength(v)


class EmailRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class TokenConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class PasswordReset(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return _check_strength(v)


class PasswordChange(BaseModel):
    current_password: str | None = Field(default=None, max_length=128, description="Omit only for Google-only accounts")
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return _check_strength(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096, description="Google Identity Services ID token (JWT)")
    language: LanguageCode | None = None
    consent: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=2048)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    is_new_user: bool = False


UserType = Literal["first_time_investor", "student", "working_professional", "senior_citizen", "other"]


class UserUpdate(BaseModel):
    name: clean(120) | None = None
    language: LanguageCode | None = None
    city: clean(80) | None = None
    state: IndianState | None = None
    user_type: UserType | None = None
    email: EmailStr | None = Field(None, description="Add an email to a phone-only account (verification is sent)")


class PhoneOTPRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=20, examples=["9820144120", "+919820144120"])
    language: LanguageCode | None = None


class PhoneLogin(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    code: str = Field(pattern=r"^\d{4,8}$")
    # Used only when this number creates a new account:
    name: clean(120) | None = None
    language: LanguageCode | None = None
    city: clean(80) | None = None
    state: IndianState | None = None
    user_type: UserType | None = None
    consent: bool = False


class PhoneLink(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    code: str = Field(pattern=r"^\d{4,8}$")


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|educator|admin)$")
