"""Shared FastAPI dependencies: DB session, authentication and RBAC."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models import User
from backend.models.enums import Role
from backend.security.jwt import TokenError, decode_token
from backend.security.rbac import has_permission, has_role
from backend.services.auth_service import token_still_valid

bearer = HTTPBearer(auto_error=False, description="JWT access token from /auth/login")

DB = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    try:
        payload = decode_token(creds.credentials, "access")
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError) as exc:
        raise _unauthorized(str(exc)) from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("User not found or inactive")
    if not token_still_valid(user, payload.get("iat")):
        raise _unauthorized("Session expired after a password change. Please log in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_consented_user(user: CurrentUser) -> User:
    """Endpoints that process personal content (scans, chat, voice, family) need prior consent."""
    from backend.config import settings

    if settings.REQUIRE_CONSENT and user.consent_version != settings.CONSENT_VERSION:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            {"code": "consent_required", "version": settings.CONSENT_VERSION, "notice": "/privacy"},
        )
    return user


ConsentedUser = Annotated[User, Depends(get_consented_user)]


def require_role(role: Role):
    def checker(user: CurrentUser) -> User:
        if not has_role(user.role, role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return checker


def require_permission(permission: str):
    def checker(user: CurrentUser) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return user

    return checker


def user_language(user: User, requested: str | None) -> str:
    return requested or user.language or "en"
