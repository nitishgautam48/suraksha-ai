"""How sure are we? A plain-language confidence level for every analysis.

Suraksha AI is a screening tool, not an oracle. Every result says how confident it is, why, and
where the user can verify independently (1930, cybercrime.gov.in, SEBI, their bank).
"""

from __future__ import annotations

from typing import Any

from backend import i18n
from backend.config import settings

# Languages whose phrasing the rule engine knows well (English, Hinglish and Devanagari scripts).
RULE_LANGUAGES = {"en", "hi", "mr"}
LEVELS = ("low", "medium", "high")

VERIFY_LINKS = [
    ("verify_1930", {"tel": "tel:1930"}),
    ("verify_portal", {"url": "https://cybercrime.gov.in"}),
    ("verify_sebi", {"url": "https://www.sebi.gov.in/intermediaries.html"}),
    ("verify_bank", {}),
]


def _near_boundary(score: int, margin: int = 6) -> bool:
    cuts = (settings.RISK_MEDIUM_THRESHOLD, settings.RISK_HIGH_THRESHOLD, settings.RISK_CRITICAL_THRESHOLD)
    return any(abs(score - c) < margin for c in cuts)


def assess(result: dict[str, Any], language: str = "en", source: str = "text", ocr_chars: int | None = None) -> dict:
    """Return {level, label, reasons, reason_texts, note, verify} for an analysis result dict."""
    level = 2  # start at "high" and step down for each source of doubt
    reasons: list[str] = []
    text = result.get("cleaned_text") or ""
    flags = len(result.get("warning_flags") or result.get("highlights") or [])
    rule, llm, score = result.get("rule_score", 0), result.get("llm_score"), result.get("risk_score", 0)

    if not result.get("llm_used"):
        level = min(level, 1)
        reasons.append("ai_unavailable")
        if language not in RULE_LANGUAGES and flags == 0:
            level = 0
            reasons.append("language_limited")
    elif language not in RULE_LANGUAGES and flags == 0 and score >= settings.RISK_MEDIUM_THRESHOLD:
        level = min(level, 1)
        reasons.append("language_limited")
    if llm is not None:
        gap = abs(rule - llm)
        if gap > 35:
            level = 0
            reasons.append("signals_disagree")
        elif gap > 20:
            level = min(level, 1)
            reasons.append("signals_disagree")
    if len(text.strip()) < 40:
        level -= 1
        reasons.append("short_text")
    if _near_boundary(score):
        level -= 1
        reasons.append("near_boundary")
    if source in ("image", "pdf") and ocr_chars is not None and ocr_chars < 80:
        level -= 1
        reasons.append("little_text")
    if flags >= 3 and score >= settings.RISK_HIGH_THRESHOLD and not reasons:
        reasons.append("strong_signals")

    name = LEVELS[max(level, 0)]
    keys = {
        "ai_unavailable": "conf_ai_unavailable",
        "language_limited": "conf_language_limited",
        "signals_disagree": "conf_signals_disagree",
        "short_text": "conf_short_text",
        "near_boundary": "conf_near_boundary",
        "little_text": "conf_little_text",
        "strong_signals": "conf_strong_signals",
    }
    return {
        "level": name,
        "label": i18n.t(f"confidence_{name}", language),
        "reasons": reasons,
        "reason_texts": [i18n.t(keys[r], language) for r in reasons],
        "note": i18n.t("uncertainty_note", language),
        "verify": [{"label": i18n.t(key, language), **extra} for key, extra in VERIFY_LINKS],
    }


def privacy(redactions: dict[str, int] | None, language: str = "en") -> dict:
    """What was hidden before analysis, as counts plus one localized sentence."""
    redactions = {k: v for k, v in (redactions or {}).items() if v}
    note = None
    if redactions:
        items = ", ".join(i18n.t(f"red_{k}", language) for k in redactions)
        note = i18n.t("redacted_note", language, items=items)
    return {"redacted": redactions, "note": note}
