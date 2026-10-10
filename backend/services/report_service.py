"""'Report this scam': a ready-to-paste complaint summary plus the official reporting steps.

Suraksha AI never files complaints itself. It prepares the text and links so the user can report
on the official channels: 1930, cybercrime.gov.in, Sanchar Saathi (Chakshu), their bank, SEBI SCORES.
The summary is in English because that is what the national portal and police work with; the
steps around it are in the user's language. Sensitive numbers were already masked at analysis time.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend import i18n
from backend.ai.risk_engine import category_label
from backend.ai.url_analysis import extract_links, extract_phone_numbers
from backend.models import ScamAnalysis
from backend.services.audit_service import record_audit
from backend.services.gamification_service import award

UPI_ID = re.compile(r"\b[\w.\-]{2,64}@[a-z]{2,20}\b(?!\.)", re.IGNORECASE)
SOURCE_NAMES = {
    "message": "message",
    "text": "message",
    "image": "screenshot",
    "pdf": "document",
    "social": "social media post",
    "link": "shared link",
}
STEPS = [
    ("report_step_1930", {"tel": "tel:1930"}, ("low", "medium", "high", "critical")),
    ("report_step_portal", {"url": "https://cybercrime.gov.in"}, ("medium", "high", "critical")),
    ("report_step_chakshu", {"url": "https://sancharsaathi.gov.in/sfc/"}, ("medium", "high", "critical")),
    ("report_step_bank", {}, ("medium", "high", "critical")),
    ("report_step_sebi", {"url": "https://scores.sebi.gov.in"}, ("investment",)),
]
INVESTMENT_CATEGORIES = {"fake_advisor", "pump_and_dump", "ponzi_scheme", "guaranteed_returns"}


def _get(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> ScamAnalysis:
    a = db.get(ScamAnalysis, analysis_id)
    if a is None or a.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    return a


def identifiers(text: str) -> dict[str, list[str]]:
    """Scammer identifiers worth reporting: phone numbers, UPI IDs, links."""
    text = text or ""
    return {
        "phones": extract_phone_numbers(text)[:5],
        "upi_ids": list(dict.fromkeys(m.group(0) for m in UPI_ID.finditer(text)))[:5],
        "links": [link.url for link in extract_links(text)][:5],
    }


def build_report(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID, language: str) -> dict[str, Any]:
    a = _get(db, user_id, analysis_id)
    ids = identifiers(a.input_excerpt or "")
    cats = [category_label(c) for c in (a.categories or [])] or ["a possible scam"]
    when = (a.created_at or datetime.now(UTC)).strftime("%d %b %Y, %H:%M UTC")
    parts = [
        f"On {when} I received a suspicious {SOURCE_NAMES.get(a.source_type, 'message')}"
        + (f" on {a.platform}" if a.platform and a.platform != "other" else "")
        + f". Suraksha AI rated it {a.risk_level.upper()} risk ({a.risk_score}/100): {', '.join(cats)}."
    ]
    if ids["phones"]:
        parts.append("Phone numbers used: " + ", ".join(ids["phones"]) + ".")
    if ids["upi_ids"]:
        parts.append("UPI IDs used: " + ", ".join(ids["upi_ids"]) + ".")
    if ids["links"]:
        parts.append("Links used: " + ", ".join(ids["links"]) + ".")
    if a.input_excerpt:
        parts.append(f'Message (my sensitive numbers hidden as ••••): "{a.input_excerpt}"')
    parts.append("Amount lost (if any): ____  Date/time of payment: ____  Transaction ID: ____")

    investment = bool(INVESTMENT_CATEGORIES & set(a.categories or []))
    steps = []
    for key, link, when_levels in STEPS:
        if when_levels == ("investment",):
            if not investment:
                continue
        elif a.risk_level not in when_levels:
            continue
        steps.append({"key": key, "text": i18n.t(key, language), **link})
    return {
        "analysis_id": a.id,
        "risk_level": a.risk_level,
        "title": i18n.t("report_title", language),
        "intro": i18n.t("report_intro", language),
        "summary_language": "en",
        "summary": "\n".join(parts),
        "identifiers": ids,
        "steps": steps,
        "reported_at": a.reported_at,
    }


def mark_reported(db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID) -> datetime:
    a = _get(db, user_id, analysis_id)
    if a.reported_at is None:
        a.reported_at = datetime.now(UTC)
        award(db, user_id, "report", ref=str(a.id))
        db.commit()
        record_audit("analysis.reported", user_id, details={"analysis_id": str(a.id), "level": a.risk_level})
    return a.reported_at
