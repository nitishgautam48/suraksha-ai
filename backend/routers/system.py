"""Health checks, task status and account data export."""

import hmac

from fastapi import APIRouter, Header, HTTPException, Response, status
from sqlalchemy import select, text

from backend.ai.ollama_client import get_ollama
from backend.api.deps import DB, CurrentUser
from backend.config import settings
from backend.models import ChatHistory, LearningProgress, SafetyAlert, ScamAnalysis
from backend.rag import store
from backend.schemas.auth import UserOut
from backend.schemas.preferences import Preferences, PreferencesUpdate
from backend.services import preferences
from backend.utils.cache import cache_get, redis_ping, task_owner_key
from backend.utils.metrics import render_latest

router = APIRouter(tags=["System"])


@router.get("/metrics", include_in_schema=False)
def metrics(authorization: str | None = Header(default=None)):
    """Prometheus scrape endpoint. Protect with METRICS_TOKEN or keep it off the public network."""
    if not settings.METRICS_ENABLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if settings.METRICS_TOKEN and not hmac.compare_digest(authorization or "", f"Bearer {settings.METRICS_TOKEN}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid metrics token")
    body, content_type = render_latest()
    return Response(body, media_type=content_type)


@router.get("/languages")
def languages():
    """The 12 supported languages. `tts` marks languages with a server voice; elsewhere use the
    device's speech synthesis with `speech_tag`."""
    from backend import i18n
    from backend.voice.tts import tts_languages

    voices = tts_languages()
    return [{**lang, "tts": lang["code"] in voices} for lang in i18n.catalog()]


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/health/ready")
def ready(db: DB):
    """Readiness: database is required; AI components report their state (the API degrades
    gracefully to rule-based analysis while models are still downloading)."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    ollama = get_ollama()
    models = ollama.list_models(max_age=0)
    want = [settings.OLLAMA_PRIMARY_MODEL, settings.OLLAMA_SECONDARY_MODEL, settings.OLLAMA_EMBED_MODEL]
    body = {
        "database": db_ok,
        "redis": redis_ping(),
        "ollama": ollama.ping(),
        "models": {m: ollama.has_model(m) for m in want},
        "chromadb": store.ping(),
        "knowledge_chunks": max(store.count(), 0),
        "available_models": sorted(models),
    }
    if not db_ok:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, body)
    return {"status": "ready", **body}


@router.get("/tasks/{task_id}")
def task_status(task_id: str, user: CurrentUser):
    """Poll an asynchronous scan (POST /scan/image or /scan/pdf with async=true)."""
    from backend.workers.celery_app import celery_app

    if cache_get(task_owner_key(task_id)) != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    res = celery_app.AsyncResult(task_id)
    payload = {"task_id": task_id, "state": res.state}
    if res.ready():
        payload["result"] = res.result if isinstance(res.result, dict) else {"status": "error", "detail": "Task failed"}
    return payload


@router.get("/me/export")
def export_my_data(user: CurrentUser, db: DB):
    """Download your scans, alerts, chats and learning progress as JSON."""

    def rows(model, *cols):
        return [{c: getattr(r, c) for c in cols} for r in db.scalars(select(model).where(model.user_id == user.id)).all()]

    return {
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "scans": rows(
            ScamAnalysis, "id", "risk_score", "risk_level", "source_type", "categories", "reasons", "input_excerpt", "created_at"
        ),
        "alerts": rows(SafetyAlert, "id", "alert_type", "severity", "title", "message", "is_read", "created_at"),
        "chats": rows(ChatHistory, "id", "message", "response", "language", "created_at"),
        "learning": rows(LearningProgress, "course_id", "completion", "best_score", "updated_at"),
    }


@router.get("/me/preferences", response_model=Preferences, tags=["Preferences"])
def get_preferences(user: CurrentUser):
    """Appearance, elder mode, notifications and privacy settings."""
    return preferences.get(user)


@router.patch("/me/preferences", response_model=Preferences, tags=["Preferences"])
def update_preferences(data: PreferencesUpdate, user: CurrentUser, db: DB):
    """Elder mode switches on larger text and spoken replies by default, simplifies explanations, and
    lets family be alerted for high-risk (not only critical) scams when auto_alert_family is on."""
    prefs = preferences.update(user, data.model_dump(exclude_none=True))
    db.commit()
    return prefs


# ---- privacy notice and consent ---------------------------------------------------------------
PRIVACY_POINTS = (
    "privacy_collect",
    "privacy_redact",
    "privacy_uploads",
    "privacy_local_ai",
    "privacy_retention",
    "privacy_never",
    "privacy_family",
    "privacy_rights",
    "privacy_no_advice",
)


@router.get("/privacy", tags=["Privacy"])
def privacy_notice(language: str = "en"):
    """Plain-language privacy notice in any of the 12 languages. Users accept it at sign-up
    (`consent: true`) or later with POST /me/consent; content endpoints return 428 until then."""
    from backend import i18n

    lang = language if language in i18n.LANGUAGES else "en"
    days = settings.ANALYSIS_RETENTION_DAYS
    return {
        "version": settings.CONSENT_VERSION,
        "language": lang,
        "title": i18n.t("privacy_title", lang),
        "points": [i18n.t(k, lang, days=days) if k == "privacy_retention" else i18n.t(k, lang) for k in PRIVACY_POINTS],
        "consent_label": i18n.t("consent_label", lang),
        "retention_days": days,
        "helplines": {"cyber_fraud": "1930", "portal": "https://cybercrime.gov.in"},
    }


@router.post("/me/consent", response_model=UserOut, tags=["Privacy"])
def give_consent(user: CurrentUser, db: DB, version: str | None = None):
    """Record acceptance of the current privacy notice."""
    from backend.services.audit_service import record_audit
    from backend.services.auth_service import record_consent

    if version and version != settings.CONSENT_VERSION:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The current notice is version {settings.CONSENT_VERSION}")
    record_consent(user)
    db.commit()
    db.refresh(user)
    record_audit("privacy.consent", user.id, details={"version": user.consent_version})
    return user
