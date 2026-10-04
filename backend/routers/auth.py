import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from backend.api.deps import DB, CurrentUser, bearer
from backend.config import settings
from backend.models import User
from backend.schemas.auth import (
    EmailRequest,
    GoogleLoginRequest,
    LoginRequest,
    PasswordChange,
    PasswordReset,
    PhoneLink,
    PhoneLogin,
    PhoneOTPRequest,
    RefreshRequest,
    RegisterRequest,
    TokenConfirm,
    TokenResponse,
    UserOut,
    UserUpdate,
)
from backend.schemas.common import Message
from backend.security.jwt import TokenError, decode_token, revoke
from backend.security.rate_limit import limiter
from backend.services import auth_service, preferences
from backend.services.audit_service import record_audit
from backend.services.file_service import delete_user_files
from backend.utils.phone import mask_phone

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def register(request: Request, data: RegisterRequest, db: DB):
    """Create an account with email + password and return JWT tokens."""
    return auth_service.issue_tokens(auth_service.register(db, data))


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def login(request: Request, data: LoginRequest, db: DB):
    return auth_service.issue_tokens(auth_service.authenticate(db, data.email, data.password, _ip(request)))


@router.post("/google", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def google(request: Request, data: GoogleLoginRequest, db: DB):
    """Sign in with a Google Identity Services ID token (OAuth 2.0 / OpenID Connect)."""
    return auth_service.issue_tokens(
        auth_service.google_login(db, data.id_token, data.language, _ip(request), consent=data.consent)
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def refresh(request: Request, data: RefreshRequest, db: DB):
    """Exchange a refresh token for a new token pair (the old refresh token is revoked)."""
    try:
        payload = decode_token(data.refresh_token, "refresh")
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (TokenError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    if not auth_service.token_still_valid(user, payload.get("iat")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired after a password change. Please log in again.")
    revoke(payload)
    return auth_service.issue_tokens(user)


@router.post("/logout", response_model=Message)
def logout(user: CurrentUser, creds: HTTPAuthorizationCredentials | None = Depends(bearer), body: RefreshRequest | None = None):
    """Revoke the current access token (and the refresh token, if supplied)."""
    if creds:
        try:
            revoke(decode_token(creds.credentials, "access"))
        except TokenError:
            pass
    if body:
        try:
            revoke(decode_token(body.refresh_token, "refresh"))
        except TokenError:
            pass
    record_audit("auth.logout", user.id)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(data: UserUpdate, user: CurrentUser, db: DB):
    changes = data.model_dump(exclude_none=True)
    new_email = changes.pop("email", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if "user_type" in changes:
        preferences.apply_user_type(user)
    if new_email and new_email.lower() != (user.email or ""):
        if auth_service.get_by_email(db, new_email):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user.email, user.email_verified, user.email_verified_at = new_email.lower(), False, None
    db.commit()
    db.refresh(user)
    if new_email:
        auth_service.send_verification(db, user)
    return user


@router.delete("/me", response_model=Message)
def delete_me(user: CurrentUser, db: DB, creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    """Permanently delete your account and all associated data (scans, files, chats, progress)."""
    user_id = user.id
    db.delete(user)
    db.commit()
    delete_user_files(user_id)
    if creds:
        try:
            revoke(decode_token(creds.credentials, "access"))
        except TokenError:
            pass
    record_audit("auth.account_deleted", user_id)
    return {"detail": "Account deleted"}


GENERIC_EMAIL_REPLY = "If an account exists for that email, a message is on its way."


@router.post("/verify-email/request", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def request_verification(request: Request, data: EmailRequest, db: DB):
    """(Re)send the email-verification link. The response never reveals whether the account exists."""
    auth_service.request_verification(db, data.email)
    return {"detail": GENERIC_EMAIL_REPLY}


@router.post("/verify-email/confirm", response_model=UserOut)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def confirm_verification(request: Request, data: TokenConfirm, db: DB):
    """Confirm the token from the verification email."""
    return auth_service.confirm_verification(db, data.token)


@router.post("/password/forgot", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def forgot_password(request: Request, data: EmailRequest, db: DB):
    """Email a single-use password-reset link (valid for PASSWORD_RESET_EXPIRE_MINUTES)."""
    auth_service.forgot_password(db, data.email, _ip(request))
    return {"detail": GENERIC_EMAIL_REPLY}


@router.post("/password/reset", response_model=Message)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def reset_password(request: Request, data: PasswordReset, db: DB):
    """Set a new password using the emailed token. All existing sessions are signed out."""
    auth_service.reset_password(db, data.token, data.new_password, _ip(request))
    return {"detail": "Password updated. Please log in with your new password."}


@router.post("/password/change", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def change_password(request: Request, data: PasswordChange, user: CurrentUser, db: DB):
    """Change password while logged in. Other sessions are signed out; fresh tokens are returned."""
    user = auth_service.change_password(db, user, data.current_password, data.new_password, _ip(request))
    return auth_service.issue_tokens(user)


# ---- Phone + OTP -----------------------------------------------------------------------------------
@router.post("/phone/request-otp", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def phone_request_otp(request: Request, data: PhoneOTPRequest):
    """Send a one-time code by SMS for phone login / sign-up (5-minute validity, 5 attempts)."""
    phone = auth_service.request_phone_otp(data.phone, "login", data.language or "en", _ip(request))
    return {"detail": f"Code sent to {mask_phone(phone)}"}


@router.post("/phone/verify", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def phone_verify(request: Request, data: PhoneLogin, db: DB):
    """Verify the code. Existing numbers log in; new numbers get an account (`is_new_user: true` -
    show the profile step and save it with PATCH /auth/me)."""
    profile = data.model_dump(include={"name", "language", "city", "state", "user_type", "consent"}, exclude_none=True)
    user, is_new = auth_service.phone_login(db, data.phone, data.code, profile, _ip(request))
    return auth_service.issue_tokens(user, is_new)


@router.post("/phone/link/request", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def phone_link_request(request: Request, data: PhoneOTPRequest, user: CurrentUser):
    """Add or change the phone number on your account (a code is sent to the new number)."""
    phone = auth_service.request_phone_otp(data.phone, f"link:{user.id}", user.language, _ip(request))
    return {"detail": f"Code sent to {mask_phone(phone)}"}


@router.post("/phone/link/confirm", response_model=UserOut)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def phone_link_confirm(request: Request, data: PhoneLink, user: CurrentUser, db: DB):
    return auth_service.link_phone(db, user, data.phone, data.code)
