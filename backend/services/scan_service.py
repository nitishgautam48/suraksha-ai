"""Module 1-3 orchestration: OCR -> cleaning -> rules -> LLM -> score -> persistence + alerts."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.ai import confidence, official_guidance
from backend.ai.analyzer import AnalysisResult, analyze_content, analyze_social
from backend.models import ScamAnalysis, UploadedFile, User
from backend.ocr.tesseract import OCRUnavailable, ocr_image, ocr_pdf
from backend.security.sanitize import strip_html
from backend.services import messages, preferences
from backend.services.activity_service import record_activity
from backend.services.alert_service import alerts_for_analysis
from backend.services.file_service import discard_file, read_file
from backend.services.gamification_service import award
from backend.utils.metrics import ANALYSES
from backend.utils.text import excerpt


def _is_elder(db: Session, user_id: uuid.UUID) -> bool:
    user = db.get(User, user_id)
    return bool(user and preferences.is_elder(user))


def simple_verdict(db: Session, user_id: uuid.UUID, level: str, language: str) -> dict[str, Any]:
    """Big-print one-line verdict + action (shown prominently in elder mode), with who to call."""
    from backend.services.family_service import list_contacts

    call = None
    if level in ("medium", "high", "critical"):
        contacts = list_contacts(db, user_id)
        if contacts:
            c = contacts[0]
            call = {"label": messages.text("call_contact", language, name=c.name), "name": c.name, "tel": f"tel:{c.phone}"}
        elif level != "medium":
            call = {"label": "1930", "name": "National Cyber Crime Helpline", "tel": "tel:1930"}
    return {
        "level": level,
        "headline": messages.text(f"verdict_{level}", language),
        "action": messages.text(f"action_{level}", language),
        "call": call,
        "elder_mode": _is_elder(db, user_id),
    }


def _engine(r: dict[str, Any]) -> dict[str, Any]:
    return {"rule_score": r["rule_score"], "llm_score": r["llm_score"], "llm_used": r["llm_used"], "model": r["model"]}


def trust(r: dict[str, Any], language: str, source: str = "text", ocr_chars: int | None = None) -> dict[str, Any]:
    """Confidence (how sure we are, and where to verify), what was redacted before analysis, and what
    the regulators say about the signals found."""
    return {
        "confidence": confidence.assess(r, language, source, ocr_chars),
        "privacy": confidence.privacy(r.get("redactions"), language),
        "official_guidance": guidance(r, language),
    }


def guidance(r: dict[str, Any], language: str) -> list[dict]:
    items = [official_guidance.get(i) for i in r.get("official_guidance") or []]
    return official_guidance.as_payload([g for g in items if g], language)


def persist_analysis(
    db: Session,
    user_id: uuid.UUID,
    result: dict[str, Any],
    source_type: str,
    text: str,
    platform: str | None = None,
    file_id: uuid.UUID | None = None,
) -> ScamAnalysis:
    analysis = ScamAnalysis(
        user_id=user_id,
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        source_type=source_type,
        platform=platform,
        categories=result.get("categories", []),
        reasons=result.get("reasons", []),
        safe_practices=result.get("safe_practices", []),
        explanation=result.get("explanation"),
        input_excerpt=strip_html(excerpt(text)),
        file_id=file_id,
        llm_used=result.get("llm_used", False),
    )
    db.add(analysis)
    db.flush()
    ANALYSES.labels(source_type, analysis.risk_level, str(analysis.llm_used).lower()).inc()
    alerts_for_analysis(db, analysis, result.get("links", []))
    award(db, user_id, "scan")
    from backend.services.family_service import auto_alert_for_analysis

    auto_alert_for_analysis(db, analysis)
    record_activity(db, user_id, "scan")
    db.commit()
    db.refresh(analysis)
    return analysis


def analyze_text(
    db: Session, user_id: uuid.UUID, text: str, language: str, source: str = "text"
) -> tuple[ScamAnalysis, AnalysisResult]:
    result = analyze_content(text, source=source, language=language, elder=_is_elder(db, user_id))
    analysis = persist_analysis(db, user_id, result.to_dict(), source, result.cleaned_text or text)
    return analysis, result


def scan_response(
    analysis: ScamAnalysis,
    result: AnalysisResult,
    extracted: str | None = None,
    ocr: dict | None = None,
    language: str = "en",
) -> dict:
    r = result.to_dict()
    ocr_chars = ocr["characters"] if ocr else None
    return trust(r, language, analysis.source_type, ocr_chars) | {
        "analysis_id": analysis.id,
        "file_id": analysis.file_id,
        "risk_level": r["risk_level"],
        "risk_score": r["risk_score"],
        "reasons": r["reasons"],
        "safe_practices": r["safe_practices"],
        "categories": r["categories"],
        "explanation": r["explanation"],
        "warning_flags": r["warning_flags"],
        "links": r["links"],
        "extracted_text": extracted,
        "ocr": ocr,
        "engine": _engine(r),
    }


def process_file(db: Session, file: UploadedFile, language: str) -> dict:
    """OCR an uploaded image/PDF and analyse it. Used inline and by the Celery worker."""
    data = read_file(file)
    try:
        ocr = ocr_image(data, language) if file.file_type == "image" else ocr_pdf(data, language)
    except OCRUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    # Privacy by design: once the text is read, the screenshot / PDF itself is no longer needed.
    discard_file(db, file)
    if not ocr.text.strip():
        raise HTTPException(422, "No readable text was found in the file")
    result = analyze_content(ocr.text, source=file.file_type, language=language, elder=_is_elder(db, file.user_id))
    analysis = persist_analysis(db, file.user_id, result.to_dict(), file.file_type, result.cleaned_text, file_id=file.id)
    ocr_info = {"pages": ocr.pages, "method": ocr.method, "languages": ocr.languages, "characters": len(ocr.text)}
    out = scan_response(analysis, result, extracted=result.cleaned_text[:5000], ocr=ocr_info, language=language)
    out["simple_verdict"] = simple_verdict(db, file.user_id, analysis.risk_level, language)
    return out


def message_response(analysis: ScamAnalysis, result: AnalysisResult, language: str = "en") -> dict:
    r = result.to_dict()
    return trust(r, language, "message") | {
        "analysis_id": analysis.id,
        "risk_score": r["risk_score"],
        "risk_level": r["risk_level"],
        "warning_flags": r["warning_flags"],
        "explanation": r["explanation"],
        "reasons": r["reasons"],
        "safe_practices": r["safe_practices"],
        "highlights": r["highlights"],
        "links": r["links"],
        "phone_numbers": r["phone_numbers"],
        "engine": _engine(r),
    }


def analyze_social_post(db: Session, user_id: uuid.UUID, text: str, platform: str, language: str) -> dict:
    r = analyze_social(text, platform, language)
    analysis = persist_analysis(
        db,
        user_id,
        {**r, "reasons": list(dict.fromkeys(h["why"] for h in r["highlights"]))[:8] or ["No manipulation tactics detected."]},
        "social",
        r["cleaned_text"],
        platform=platform,
    )
    return trust(r, language, "social") | {
        "simple_verdict": simple_verdict(db, user_id, r["risk_level"], language),
        "analysis_id": analysis.id,
        "platform": platform,
        "risk_score": r["risk_score"],
        "risk_level": r["risk_level"],
        "tactics": r["tactics"],
        "highlights": r["highlights"],
        "segments": r["segments"],
        "explanation": r["explanation"],
        "safe_practices": r["safe_practices"],
        "links": r["links"],
        "engine": _engine(r),
    }


def quick_preview(text: str, kind: str, platform: str, language: str) -> dict:
    """Instant rules-only result, shown while the AI review runs. Not stored, no XP, no alerts.

    The full result can only score the same or higher (final = max(rules, blend)), so the preview
    never tells the user something is safer than the final answer will."""
    if kind == "social":
        r = analyze_social(text, platform, language, use_llm=False)
        keys = ("risk_score", "risk_level", "tactics", "highlights", "segments", "explanation", "safe_practices", "links")
    else:
        r = analyze_content(text, source="message" if kind == "message" else "text", language=language, use_llm=False).to_dict()
        keys = ("risk_score", "risk_level", "warning_flags", "highlights", "explanation", "reasons", "safe_practices", "links")
    return {k: r[k] for k in keys} | {
        "analysis_id": None,
        "preliminary": True,
        "privacy": confidence.privacy(r.get("redactions"), language),
        "official_guidance": guidance(r, language),
        "engine": _engine(r),
    }
