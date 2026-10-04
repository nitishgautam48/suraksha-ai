"""Hybrid scam analysis: deterministic rules + local LLM (Ollama) reasoning.

Pipeline: content cleaning -> rule-based risk detection -> LLM analysis -> score fusion.
If the LLM is unavailable the rule engine alone still returns a complete, explainable result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend import i18n
from backend.ai import official_guidance, prompts
from backend.ai.guardrails import output_violates_policy
from backend.ai.ollama_client import LLMUnavailable, get_ollama, model_for
from backend.ai.patterns import RISK_CATEGORIES
from backend.ai.risk_engine import RuleResult, analyze_rules, category_label, level_for, safe_practices_for
from backend.config import settings
from backend.utils.cache import cache_get, cache_key, cache_set
from backend.utils.logging import get_logger
from backend.utils.redact import redact
from backend.utils.text import clean_text

log = get_logger(__name__)


@dataclass
class AnalysisResult:
    risk_score: int
    risk_level: str
    categories: list[str]
    reasons: list[str]
    safe_practices: list[str]
    explanation: str
    warning_flags: list[dict[str, Any]]
    highlights: list[dict[str, Any]]
    links: list[dict[str, Any]]
    phone_numbers: list[str]
    rule_score: int
    llm_score: int | None
    llm_used: bool
    model: str | None
    cleaned_text: str = field(repr=False, default="")
    redactions: dict[str, int] = field(default_factory=dict)  # secrets hidden before analysis
    official_guidance: list[str] = field(default_factory=list)  # ids in backend.ai.official_guidance

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _template_explanation(rules: RuleResult, level: str, language: str) -> str:
    lead = i18n.t(f"level_{level}", language)
    if not rules.flags and not rules.risky_links:
        return lead
    labels = ", ".join(dict.fromkeys(f.label for f in rules.flags)) or "suspicious links"
    if language == "en":
        return f"{lead} Detected signals: {labels}."
    return f"{lead} ({labels})"


def _str_list(value: Any, limit: int = 6, max_len: int = 300) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:max_len])
    return out[:limit]


def _signals(rules: RuleResult, extra: list[str] | None = None) -> set[str]:
    return {f.key for f in rules.flags} | set(rules.categories) | set(extra or [])


def _guidance_for_prompt(rules: RuleResult, text: str) -> str:
    return official_guidance.for_prompt(official_guidance.select(_signals(rules), text, "medium" if rules.flags else "low"))


def _llm_analyse(text: str, source: str, rules: RuleResult, language: str, elder: bool = False) -> dict[str, Any] | None:
    key = cache_key("scan", settings.OLLAMA_PRIMARY_MODEL, source, language, str(elder), text)
    if (cached := cache_get(key)) is not None:
        return cached
    user = prompts.SCAM_ANALYST_USER.format(
        source=source,
        rule_flags=", ".join(f.label for f in rules.flags) or "none",
        links="; ".join(f"{link.host} ({', '.join(link.issues) or 'no issues'})" for link in rules.links) or "none",
        content=text[:6000],
        language=prompts.LANGUAGE_NAMES.get(language, "English"),
        guidance=_guidance_for_prompt(rules, text),
    )
    try:
        system = prompts.SCAM_ANALYST_SYSTEM + (prompts.ELDER_STYLE if elder else "")
        data = get_ollama().chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model_for(language),
            max_tokens=settings.SCAN_MAX_TOKENS,
        )
    except LLMUnavailable as exc:
        log.info("LLM unavailable for scan analysis, using rules only: %s", exc)
        return None
    try:
        score = max(0, min(100, int(float(data.get("risk_score", 0)))))
    except (TypeError, ValueError):
        return None
    result = {
        "risk_score": score,
        "categories": [c for c in _str_list(data.get("categories"), 8) if c in RISK_CATEGORIES],
        "reasons": _str_list(data.get("reasons")),
        "safe_practices": [p for p in _str_list(data.get("safe_practices")) if not output_violates_policy(p)],
        "explanation": str(data.get("explanation") or "").strip()[:1500],
    }
    if output_violates_policy(result["explanation"]):
        result["explanation"] = ""
    cache_set(key, result)
    return result


def _fuse(rule_score: int, llm_score: int | None) -> int:
    if llm_score is None:
        return rule_score
    w = settings.RISK_LLM_WEIGHT
    blended = round((1 - w) * rule_score + w * llm_score)
    return max(rule_score, blended)


def analyze_content(
    text: str, source: str = "text", language: str = "en", use_llm: bool = True, elder: bool = False
) -> AnalysisResult:
    cleaned, redactions = redact(clean_text(text))
    rules = analyze_rules(cleaned)
    llm = _llm_analyse(cleaned, source, rules, language, elder) if (use_llm and cleaned) else None

    score = _fuse(rules.score, llm["risk_score"] if llm else None)
    level = level_for(score)
    categories = list(dict.fromkeys(rules.categories + (llm["categories"] if llm else [])))
    if score < 25 and llm and not rules.flags:
        categories = []  # don't label benign content with LLM-only categories

    reasons = rules.reasons()
    if llm:
        reasons += [r for r in llm["reasons"] if r not in reasons]
    if not reasons:
        reasons = ["No common scam or manipulation patterns were detected."]

    practices = safe_practices_for(categories)
    if llm:
        practices = list(dict.fromkeys(llm["safe_practices"][:3] + practices))[:8]

    explanation = (llm or {}).get("explanation") or _template_explanation(rules, level, language)
    if elder:
        practices = practices[:3]

    return AnalysisResult(
        risk_score=score,
        risk_level=level,
        categories=categories,
        reasons=reasons[:8],
        safe_practices=practices,
        explanation=explanation,
        warning_flags=[
            {
                "key": f.key,
                "label": f.label,
                "category": f.category,
                "category_label": category_label(f.category),
                "reason": f.reason,
                "evidence": f.evidence,
            }
            for f in rules.flags
        ],
        highlights=[
            {"start": s.start, "end": s.end, "text": s.text, "signal": s.detector, "label": s.label, "category": s.category}
            for s in rules.spans
        ],
        links=[{"url": link.url, "host": link.host, "issues": link.issues, "risk": link.score} for link in rules.links],
        phone_numbers=rules.phone_numbers,
        rule_score=rules.score,
        llm_score=llm["risk_score"] if llm else None,
        llm_used=llm is not None,
        model=settings.OLLAMA_PRIMARY_MODEL if llm else None,
        cleaned_text=cleaned,
        redactions=redactions,
        official_guidance=[g.id for g in official_guidance.select(_signals(rules, categories), cleaned, level)],
    )


# ---------------------------------------------------------------------------------------------
# Social media analysis (Module 3)
# ---------------------------------------------------------------------------------------------
DETECTOR_TO_TACTIC = {
    "emotional": "emotional_manipulation",
    "fear": "emotional_manipulation",
    "fomo": "fomo",
    "urgency": "scarcity",
    "fake_success": "fake_success_stories",
    "pump_language": "pump_language",
    "impersonation": "fake_authority",
    "fake_advisor": "fake_authority",
    "guaranteed_returns": "guaranteed_returns",
    "unrealistic_profits": "guaranteed_returns",
}
TACTIC_LABELS = {
    "emotional_manipulation": "Emotional manipulation",
    "fomo": "FOMO",
    "scarcity": "Scarcity tactics",
    "fake_success_stories": "Fake success stories",
    "pump_language": "Pump language",
    "fake_authority": "Fake authority",
    "guaranteed_returns": "Guaranteed returns",
}


def _build_segments(text: str, highlights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split text into contiguous segments, marking risky ones with their tactics."""
    if not highlights:
        return [{"text": text, "risky": False, "tactics": []}] if text else []
    bounds = sorted({0, len(text)} | {h["start"] for h in highlights} | {h["end"] for h in highlights})
    segments: list[dict[str, Any]] = []
    for a, b in zip(bounds, bounds[1:], strict=False):
        if a == b:
            continue
        tactics = sorted({h["tactic"] for h in highlights if h["start"] <= a and h["end"] >= b})
        if segments and segments[-1]["tactics"] == tactics:
            segments[-1]["text"] += text[a:b]
        else:
            segments.append({"text": text[a:b], "risky": bool(tactics), "tactics": tactics})
    return segments


def analyze_social(text: str, platform: str, language: str = "en", use_llm: bool = True) -> dict[str, Any]:
    cleaned, redactions = redact(clean_text(text))
    rules = analyze_rules(cleaned)

    highlights = [
        {
            "start": s.start,
            "end": s.end,
            "text": s.text,
            "tactic": DETECTOR_TO_TACTIC[s.detector],
            "why": next(f.reason for f in rules.flags if f.key == s.detector),
            "source": "rules",
        }
        for s in rules.spans
        if s.detector in DETECTOR_TO_TACTIC
    ]

    llm: dict[str, Any] | None = None
    if use_llm and cleaned:
        key = cache_key("social", settings.OLLAMA_PRIMARY_MODEL, platform, language, cleaned)
        llm = cache_get(key)
        if llm is None:
            try:
                data = get_ollama().chat_json(
                    [
                        {"role": "system", "content": prompts.SOCIAL_SYSTEM},
                        {
                            "role": "user",
                            "content": prompts.SOCIAL_USER.format(
                                platform=platform,
                                rule_flags=", ".join(sorted({h["tactic"] for h in highlights})) or "none",
                                content=cleaned[:6000],
                                language=prompts.LANGUAGE_NAMES.get(language, "English"),
                                guidance=_guidance_for_prompt(rules, cleaned),
                            ),
                        },
                    ],
                    model=model_for(language),
                    max_tokens=settings.SCAN_MAX_TOKENS,
                )
                llm = {
                    "risk_score": max(0, min(100, int(float(data.get("risk_score", 0))))),
                    "tactics": [t for t in _str_list(data.get("tactics"), 10) if t in TACTIC_LABELS],
                    "quotes": [q for q in data.get("risky_quotes", []) if isinstance(q, dict)][:12],
                    "explanation": str(data.get("explanation") or "").strip()[:1500],
                }
                if output_violates_policy(llm["explanation"]):
                    llm["explanation"] = ""
                cache_set(key, llm)
            except (LLMUnavailable, TypeError, ValueError) as exc:
                log.info("LLM unavailable for social analysis: %s", exc)
                llm = None

    if llm:
        lowered = cleaned.lower()
        for q in llm["quotes"]:
            quote, tactic = str(q.get("quote", "")).strip(), q.get("tactic")
            if len(quote) < 4 or tactic not in TACTIC_LABELS:
                continue
            idx = lowered.find(quote.lower())
            if idx >= 0:
                highlights.append(
                    {
                        "start": idx,
                        "end": idx + len(quote),
                        "text": cleaned[idx : idx + len(quote)],
                        "tactic": tactic,
                        "why": str(q.get("why", ""))[:200],
                        "source": "llm",
                    }
                )

    highlights.sort(key=lambda h: (h["start"], h["end"]))
    tactics = sorted({h["tactic"] for h in highlights} | set(llm["tactics"] if llm else []))
    score = _fuse(rules.score, llm["risk_score"] if llm else None)
    level = level_for(score)
    explanation = (llm or {}).get("explanation") or _template_explanation(rules, level, language)

    return {
        "platform": platform,
        "risk_score": score,
        "risk_level": level,
        "tactics": [
            {"key": t, "label": TACTIC_LABELS[t], "count": sum(1 for h in highlights if h["tactic"] == t)} for t in tactics
        ],
        "highlights": highlights,
        "segments": _build_segments(cleaned, highlights),
        "explanation": explanation,
        "safe_practices": safe_practices_for(rules.categories),
        "categories": rules.categories,
        "links": [{"url": link.url, "host": link.host, "issues": link.issues, "risk": link.score} for link in rules.links],
        "rule_score": rules.score,
        "llm_score": llm["risk_score"] if llm else None,
        "llm_used": llm is not None,
        "model": settings.OLLAMA_PRIMARY_MODEL if llm else None,
        "cleaned_text": cleaned,
        "redactions": redactions,
        "official_guidance": [g.id for g in official_guidance.select(_signals(rules), cleaned, level)],
    }
