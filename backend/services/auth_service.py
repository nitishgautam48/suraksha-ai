from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import User
from backend.models.enums import Role, TokenPurpose
from backend.schemas.auth import RegisterRequest, TokenResponse, UserOut
from backend.security.jwt import create_access_token, create_refresh_token
from backend.security.passwords import hash_password, verify_password
from backend.services import email_service, messages, otp_service, preferences, sms_service, token_service
from backend.services.audit_service import record_audit
from backend.services.gamification_service import award
from backend.utils.cache import get_redis
from backend.utils.logging import get_logger
from backend.utils.phone import InvalidPhone, mask_phone, normalize_phone

log = get_logger(__name__)

# Constant-time-ish defence against user enumeration via timing.
_DUMMY_HASH = hash_password("dummy-password-1")


def issue_tokens(user: User, is_new: bool = False) -> TokenResponse:
    return TokenResponse(
        is_new_user=is_new,
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def record_consent(user: User, version: str | None = None) -> None:
    """Remember that the user accepted the privacy notice (GET /privacy) of this version."""
    user.consent_version = version or settings.CONSENT_VERSION
    user.consent_at = datetime.now(UTC)


def register(db: Session, data: RegisterRequest) -> User:
    if get_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        name=data.name,
        email=data.email,
        language=data.language,
        role=Role.USER.value,
        password_hash=hash_password(data.password),
        auth_provider="password",
    )
    if data.consent:
        record_consent(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit("auth.register", user.id, details={"provider": "password"})
    send_verification(db, user)
    return user


def authenticate(db: Session, email: str, password: str, ip: str | None) -> User:
    user = get_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        record_audit("auth.login_failed", None, ip_address=ip, details={"email": email, "reason": "unknown"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not verify_password(password, user.password_hash):
        record_audit("auth.login_failed", user.id, ip_address=ip, details={"reason": "bad_password"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified. Check your inbox or request a new link.")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    record_audit("auth.login", user.id, ip_address=ip, details={"provider": "password"})
    return user


def verify_google_token(token: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google login is not configured (GOOGLE_CLIENT_ID)")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token") from exc
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token issuer")
    if not info.get("email_verified"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google email is not verified")
    return info


def google_login(db: Session, token: str, language: str | None, ip: str | None, consent: bool = False) -> User:
    info = verify_google_token(token)
    sub, email = info["sub"], info["email"].lower()
    user = db.scalar(select(User).where(User.google_sub == sub)) or get_by_email(db, email)
    if user is None:
        user = User(
            name=(info.get("name") or email.split("@")[0])[:120],
            email=email,
            language=language or "en",
            role=Role.USER.value,
            google_sub=sub,
            auth_provider="google",
            is_active=True,
            email_verified=True,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
    if consent and user.consent_version != settings.CONSENT_VERSION:
        record_consent(user)
        action = "auth.register"
    else:
        if user.google_sub is None:
            user.google_sub = sub  # link Google to an existing (verified-email) account
        if not user.email_verified:
            user.email_verified, user.email_verified_at = True, datetime.now(UTC)
        if not user.email_verified:
            user.email_verified, user.email_verified_at = True, datetime.now(UTC)
        action = "auth.login"
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    record_audit(action, user.id, ip_address=ip, details={"provider": "google"})
    return user


def bootstrap_admin(db: Session) -> None:
    """Create the first admin from env vars if configured and missing."""
    if not (settings.BOOTSTRAP_ADMIN_EMAIL and settings.BOOTSTRAP_ADMIN_PASSWORD):
        return
    try:
        email = validate_email(settings.BOOTSTRAP_ADMIN_EMAIL, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        log.error("BOOTSTRAP_ADMIN_EMAIL is not a valid login email (%s); admin not created", exc)
        return
    user = get_by_email(db, email)
    if user is None:
        db.add(
            User(
                name="Administrator",
                email=email,
                role=Role.ADMIN.value,
                password_hash=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
                auth_provider="password",
                email_verified=True,
                email_verified_at=datetime.now(UTC),
            )
        )
        db.commit()
        log.info("Bootstrap admin created: %s", email)
    elif user.role != Role.ADMIN.value:
        user.role = Role.ADMIN.value
        db.commit()


# ---- Email verification & password reset ---------------------------------------------------
EMAIL_COOLDOWN_SECONDS = 60


def _cooldown_ok(user_id, purpose: str) -> bool:
    """At most one email per purpose per minute per user (stops mail-bombing a victim's inbox)."""
    try:
        return bool(get_redis().set(f"suraksha:mail-cooldown:{purpose}:{user_id}", "1", nx=True, ex=EMAIL_COOLDOWN_SECONDS))
    except Exception:
        return True


def _link(path: str, token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/{path}?token={quote(token)}"


def send_verification(db: Session, user: User) -> bool:
    if not user.email or user.email_verified or not _cooldown_ok(user.id, "verify"):
        return False
    raw = token_service.issue(db, user.id, TokenPurpose.VERIFY_EMAIL, timedelta(hours=settings.EMAIL_VERIFY_EXPIRE_HOURS))
    email_service.send_template(user.email, "verify_email", user.language, _link("verify-email", raw), name=user.name)
    return True


def request_verification(db: Session, email: str) -> None:
    """Public resend endpoint: identical response whether or not the account exists."""
    user = get_by_email(db, email)
    if user and user.is_active:
        send_verification(db, user)


def confirm_verification(db: Session, raw_token: str) -> User:
    user = token_service.consume(db, raw_token, TokenPurpose.VERIFY_EMAIL)
    user.email_verified, user.email_verified_at = True, datetime.now(UTC)
    award(db, user.id, "verify_email")
    db.commit()
    record_audit("auth.email_verified", user.id)
    return user


def forgot_password(db: Session, email: str, ip: str | None) -> None:
    """Always succeeds from the caller's point of view (no account enumeration)."""
    user = get_by_email(db, email)
    record_audit(
        "auth.password_reset_requested", user.id if user else None, ip_address=ip, details={"known_account": user is not None}
    )
    if user is None or not user.is_active or not _cooldown_ok(user.id, "reset"):
        return
    raw = token_service.issue(db, user.id, TokenPurpose.RESET_PASSWORD, timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES))
    email_service.send_template(user.email, "reset_password", user.language, _link("reset-password", raw), name=user.name)


def _set_password(db: Session, user: User, new_password: str) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    user.password_hash = hash_password(new_password)
    user.tokens_valid_after = now  # signs out every existing session
    db.commit()
    if user.email:
        email_service.send_template(user.email, "password_changed", user.language, name=user.name)


def reset_password(db: Session, raw_token: str, new_password: str, ip: str | None) -> User:
    user = token_service.consume(db, raw_token, TokenPurpose.RESET_PASSWORD)
    if not user.email_verified:  # receiving the reset email proves inbox ownership
        user.email_verified, user.email_verified_at = True, datetime.now(UTC)
    _set_password(db, user, new_password)
    record_audit("auth.password_reset", user.id, ip_address=ip)
    return user


def change_password(db: Session, user: User, current_password: str | None, new_password: str, ip: str | None) -> User:
    if user.password_hash and not verify_password(current_password or "", user.password_hash):
        record_audit("auth.password_change_failed", user.id, ip_address=ip)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if verify_password(new_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must differ from the current one")
    _set_password(db, user, new_password)
    record_audit("auth.password_changed", user.id, ip_address=ip)
    return user


def token_still_valid(user: User, issued_at: int | float | None) -> bool:
    if user.tokens_valid_after is None or issued_at is None:
        return True
    cutoff = user.tokens_valid_after
    cutoff = cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)
    return issued_at >= cutoff.timestamp()


# ---- Phone + OTP ---------------------------------------------------------------------------------
def _normalize(phone: str) -> str:
    try:
        return normalize_phone(phone)
    except InvalidPhone as exc:
        raise HTTPException(422, str(exc)) from exc


def request_phone_otp(phone: str, purpose: str, language: str, ip: str | None) -> str:
    phone = _normalize(phone)
    code = otp_service.issue(phone, purpose, ip)
    minutes = max(settings.OTP_TTL_SECONDS // 60, 1)
    sms_service.send_sms(phone, messages.text("otp", language, code=code, minutes=minutes), f"otp_{purpose}", {"otp": code})
    record_audit("auth.otp_requested", None, ip_address=ip, details={"phone": mask_phone(phone), "purpose": purpose})
    return phone


def phone_login(db: Session, phone: str, code: str, profile: dict, ip: str | None) -> tuple[User, bool]:
    """Verify the OTP; log in the owner of the number, or create a new account (returns is_new)."""
    phone = _normalize(phone)
    otp_service.verify(phone, "login", code)
    user = db.scalar(select(User).where(User.phone == phone))
    is_new = user is None
    if is_new:
        user = User(
            name=profile.get("name") or f"Suraksha user {phone[-4:]}",
            phone=phone,
            phone_verified=True,
            language=profile.get("language") or "en",
            city=profile.get("city"),
            state=profile.get("state"),
            user_type=profile.get("user_type"),
            role=Role.USER.value,
            auth_provider="phone",
            is_active=True,
        )
        db.add(user)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    if profile.get("consent") and user.consent_version != settings.CONSENT_VERSION:
        record_consent(user)
    user.phone_verified = True
    user.last_login_at = datetime.now(UTC)
    if is_new:
        preferences.apply_user_type(user)
    db.commit()
    if award(db, user.id, "verify_phone"):
        db.commit()
    db.refresh(user)
    record_audit("auth.register" if is_new else "auth.login", user.id, ip_address=ip, details={"provider": "phone"})
    return user, is_new


def link_phone(db: Session, user: User, phone: str, code: str) -> User:
    phone = _normalize(phone)
    otp_service.verify(phone, f"link:{user.id}", code)
    owner = db.scalar(select(User).where(User.phone == phone))
    if owner is not None and owner.id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This number is already linked to another account")
    user.phone, user.phone_verified = phone, True
    award(db, user.id, "verify_phone")
    db.commit()
    record_audit("auth.phone_linked", user.id, details={"phone": mask_phone(phone)})
    return user
