"""Transactional email over SMTP (free: any SMTP server; Mailpit is bundled for local testing)."""

from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from backend.config import settings
from backend.utils.logging import get_logger
from backend.utils.metrics import EMAILS

log = get_logger(__name__)

TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "verify_email": {
        "en": {
            "subject": "Verify your Suraksha AI email",
            "intro": "Namaste {name}, please confirm your email address to secure your Suraksha AI account.",
            "action": "Verify email",
            "outro": "This link expires in {hours} hours. If you did not create an account, ignore this email.",
        },
        "hi": {
            "subject": "अपना Suraksha AI ईमेल सत्यापित करें",
            "intro": "नमस्ते {name}, अपने Suraksha AI खाते को सुरक्षित करने के लिए अपना ईमेल पता पुष्टि करें।",
            "action": "ईमेल सत्यापित करें",
            "outro": "यह लिंक {hours} घंटे में समाप्त हो जाएगा। अगर आपने खाता नहीं बनाया है, तो इस ईमेल को अनदेखा करें।",
        },
    },
    "reset_password": {
        "en": {
            "subject": "Reset your Suraksha AI password",
            "intro": "Namaste {name}, we received a request to reset your password.",
            "action": "Reset password",
            "outro": "This link expires in {minutes} minutes and works once. If you did not ask for this, ignore this "
            "email - your password stays the same. Suraksha AI will never ask for your OTP or PIN.",
        },
        "hi": {
            "subject": "अपना Suraksha AI पासवर्ड रीसेट करें",
            "intro": "नमस्ते {name}, हमें आपका पासवर्ड रीसेट करने का अनुरोध मिला है।",
            "action": "पासवर्ड रीसेट करें",
            "outro": "यह लिंक {minutes} मिनट में समाप्त हो जाएगा और केवल एक बार काम करेगा। अगर आपने यह अनुरोध नहीं किया, "
            "तो इसे अनदेखा करें। Suraksha AI कभी भी आपका OTP या PIN नहीं माँगता।",
        },
    },
    "password_changed": {
        "en": {
            "subject": "Your Suraksha AI password was changed",
            "intro": "Namaste {name}, the password for your Suraksha AI account was just changed and all devices were signed out.",
            "action": "",
            "outro": "If this was not you, reset your password immediately and call the Cyber Crime Helpline 1930.",
        },
        "hi": {
            "subject": "आपका Suraksha AI पासवर्ड बदल दिया गया",
            "intro": "नमस्ते {name}, आपके Suraksha AI खाते का पासवर्ड अभी बदला गया और सभी डिवाइस से लॉग आउट कर दिया गया।",
            "action": "",
            "outro": "अगर यह आपने नहीं किया, तो तुरंत पासवर्ड रीसेट करें और साइबर क्राइम हेल्पलाइन 1930 पर कॉल करें।",
        },
    },
}


def render(template: str, language: str, link: str | None = None, **values: object) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body)."""
    t = TEMPLATES[template].get(language) or TEMPLATES[template]["en"]
    values = {"hours": settings.EMAIL_VERIFY_EXPIRE_HOURS, "minutes": settings.PASSWORD_RESET_EXPIRE_MINUTES, **values}
    intro, outro = t["intro"].format(**values), t["outro"].format(**values)
    text = f"{intro}\n\n" + (f"{t['action']}: {link}\n\n" if link else "") + f"{outro}\n\n- Suraksha AI"
    button = (
        f'<p><a href="{html.escape(link, quote=True)}" style="background:#4F5BF0;color:#fff;padding:12px 20px;'
        f'border-radius:8px;text-decoration:none;display:inline-block">{html.escape(t["action"])}</a></p>'
        f'<p style="font-size:12px;color:#625F80">{html.escape(link)}</p>'
        if link
        else ""
    )
    body = (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#0D0C1D">'
        f"<h2>Suraksha AI</h2><p>{html.escape(intro)}</p>{button}"
        f'<p style="font-size:13px;color:#625F80">{html.escape(outro)}</p></div>'
    )
    return t["subject"], text, body


def send_email_now(to: str, subject: str, text: str, html_body: str | None = None) -> None:
    """Send synchronously. Raises on SMTP failure (the Celery task retries)."""
    if not settings.EMAIL_ENABLED:
        log.info("EMAIL_ENABLED=false - email to %s not sent: %s", to, subject)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.EMAIL_FROM, to, subject
    msg["Message-ID"] = make_msgid(domain="suraksha.ai")
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    smtp_cls = smtplib.SMTP_SSL if settings.SMTP_SSL else smtplib.SMTP
    kwargs = {"context": context} if settings.SMTP_SSL else {}
    with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS, **kwargs) as smtp:
        if settings.SMTP_STARTTLS and not settings.SMTP_SSL:
            smtp.starttls(context=context)
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    log.info("Email sent to %s: %s", to, subject)


def send_email(to: str, subject: str, text: str, html_body: str | None = None) -> None:
    """Queue on Celery (with retries); fall back to sending inline if the broker is unavailable."""
    try:
        from backend.workers.tasks import send_email_task

        send_email_task.delay(to, subject, text, html_body)
    except Exception as exc:
        log.warning("Could not queue email (%s); sending inline", exc)
        try:
            send_email_now(to, subject, text, html_body)
        except Exception as send_exc:
            log.error("Email to %s failed: %s", to, send_exc)


def send_template(to: str, template: str, language: str, link: str | None = None, **values: object) -> None:
    subject, text, body = render(template, language, link, **values)
    EMAILS.labels(template, "queued").inc()
    send_email(to, subject, text, body)
