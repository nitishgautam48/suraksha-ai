"""Pluggable SMS delivery. Sending SMS in India always costs money, so the default providers are free
development options; configure a real gateway for production (see README "Phone login").

Note: commercial SMS to Indian numbers requires DLT-registered sender IDs and templates (TRAI).
"""

from __future__ import annotations

import httpx

from backend.config import settings
from backend.utils.logging import get_logger
from backend.utils.metrics import SMS_MESSAGES
from backend.utils.phone import mask_phone

log = get_logger(__name__)


class SMSError(Exception):
    pass


def _console(to: str, text: str, purpose: str, variables: dict) -> None:
    log.warning("SMS_PROVIDER=console - SMS to %s (%s) not delivered: %s", mask_phone(to), purpose, text)


def _email_bridge(to: str, text: str, purpose: str, variables: dict) -> None:
    """Development: deliver the SMS body as an email (lands in the Mailpit inbox)."""
    from backend.services.email_service import send_email_now

    send_email_now(f"{to.lstrip('+')}@{settings.SMS_EMAIL_BRIDGE_DOMAIN}", f"[SMS:{purpose}] to {to}", text)


def _webhook(to: str, text: str, purpose: str, variables: dict) -> None:
    if not settings.SMS_WEBHOOK_URL:
        raise SMSError("SMS_WEBHOOK_URL is not configured")
    headers = {"Authorization": f"Bearer {settings.SMS_WEBHOOK_TOKEN}"} if settings.SMS_WEBHOOK_TOKEN else {}
    r = httpx.post(
        settings.SMS_WEBHOOK_URL, json={"to": to, "message": text, "purpose": purpose, **variables}, headers=headers, timeout=15
    )
    r.raise_for_status()


def _twilio(to: str, text: str, purpose: str, variables: dict) -> None:
    sid = settings.TWILIO_ACCOUNT_SID
    r = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data={"To": to, "From": settings.TWILIO_FROM_NUMBER, "Body": text},
        auth=(sid, settings.TWILIO_AUTH_TOKEN),
        timeout=15,
    )
    r.raise_for_status()


def _msg91(to: str, text: str, purpose: str, variables: dict) -> None:
    template = settings.MSG91_OTP_TEMPLATE_ID if purpose.startswith("otp") else settings.MSG91_ALERT_TEMPLATE_ID
    if not template:
        raise SMSError("MSG91 template id not configured for " + purpose)
    r = httpx.post(
        "https://control.msg91.com/api/v5/flow",
        json={
            "template_id": template,
            "short_url": "0",
            "recipients": [{"mobiles": to.lstrip("+"), **{k: str(v) for k, v in variables.items()}}],
        },
        headers={"authkey": settings.MSG91_AUTH_KEY, "accept": "application/json"},
        timeout=15,
    )
    r.raise_for_status()


def _fast2sms(to: str, text: str, purpose: str, variables: dict) -> None:
    if not to.startswith("+91"):
        raise SMSError("Fast2SMS only delivers to Indian numbers")
    payload = (
        {"route": "otp", "variables_values": variables["otp"], "numbers": to[3:]}
        if "otp" in variables
        else {"route": "q", "message": text, "numbers": to[3:]}
    )
    r = httpx.post(
        "https://www.fast2sms.com/dev/bulkV2", json=payload, headers={"authorization": settings.FAST2SMS_API_KEY}, timeout=15
    )
    r.raise_for_status()


PROVIDERS = {
    "console": _console,
    "email_bridge": _email_bridge,
    "webhook": _webhook,
    "twilio": _twilio,
    "msg91": _msg91,
    "fast2sms": _fast2sms,
}


def send_sms_now(to: str, text: str, purpose: str, variables: dict | None = None) -> None:
    provider = PROVIDERS.get(settings.SMS_PROVIDER)
    if provider is None:
        raise SMSError(f"Unknown SMS_PROVIDER {settings.SMS_PROVIDER!r}")
    try:
        provider(to, text, purpose, variables or {})
        SMS_MESSAGES.labels(settings.SMS_PROVIDER, purpose, "sent").inc()
    except Exception as exc:
        SMS_MESSAGES.labels(settings.SMS_PROVIDER, purpose, "failed").inc()
        log.error("SMS to %s via %s failed: %s", mask_phone(to), settings.SMS_PROVIDER, exc)
        raise SMSError(str(exc)) from exc


def send_sms(to: str, text: str, purpose: str, variables: dict | None = None) -> None:
    """Queue on Celery (retries); fall back to inline delivery if the broker is down."""
    try:
        from backend.workers.tasks import send_sms_task

        send_sms_task.delay(to, text, purpose, variables or {})
    except Exception as exc:
        log.warning("Could not queue SMS (%s); sending inline", exc)
        try:
            send_sms_now(to, text, purpose, variables)
        except SMSError:
            pass
