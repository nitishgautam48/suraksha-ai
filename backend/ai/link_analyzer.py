"""Link checker: open a shared link, read it, check its claims, and give a reasoned verdict.

Pipeline: fetch (link_fetcher) -> clean + redact -> rules engine on the combined text ->
deterministic claim checks (link_checks) -> local LLM with the checks as facts -> fused score.
The AI can raise the risk but never lower the rules score, same as every other scan.
"""

from __future__ import annotations

from typing import Any

from backend.ai import link_checks, official_guidance, prompts
from backend.ai.analyzer import TACTIC_LABELS, _build_segments, _fuse, _guidance_for_prompt, _signals, _str_list, analyze_social
from backend.ai.guardrails import output_violates_policy, sanitize_llm_output
from backend.ai.link_fetcher import PLATFORM_NAMES, FetchedContent
from backend.ai.ollama_client import LLMUnavailable, get_ollama, model_for
from backend.ai.risk_engine import analyze_rules, level_for
from backend.config import settings
from backend.utils.cache import cache_get, cache_key, cache_set
from backend.utils.logging import get_logger

log = get_logger(__name__)

ASSESSMENTS = ("false", "misleading", "unverifiable", "plausible")
VERDICTS = {
    "scam": ("Likely scam", "gpp_bad"),
    "suspicious": ("Suspicious: be careful", "warning"),
    "no_signs": ("No scam signs found", "verified_user"),
    "unclear": ("Not enough information", "help"),
}
DEFAULT_STEPS = {
    "scam": [
        "Do not pay, invest or download any app this post points to.",
        "Do not join the WhatsApp / Telegram group or share your phone number.",
        "Report the post on the platform so others are protected.",
        "If you already paid, call 1930 immediately or report at cybercrime.gov.in.",
    ],
    "suspicious": [
        "Do not pay or share personal details until you have verified the claims.",
        "Check any adviser or broker on SEBI's official intermediary list.",
        "Ask a family member or use Suraksha's assistant before acting.",
    ],
    "no_signs": [
        "No scam signals were found, but always verify before paying anyone.",
        "Never share OTPs, PINs or passwords, whoever asks.",
    ],
    "unclear": [
        "Too little could be read from this link. Paste the caption or upload a screenshot to check it fully.",
        "Do not pay or join any group until you are sure.",
    ],
}


def _llm(fc: FetchedContent, cleaned: str, rule_tactics: list[str], checks: list[dict], rules, language: str) -> dict | None:
    key = cache_key("link", settings.OLLAMA_PRIMARY_MODEL, language, fc.platform, cleaned)
    if (cached := cache_get(key)) is not None:
        return cached
    user = prompts.LINK_USER.format(
        platform=PLATFORM_NAMES.get(fc.platform, "Website"),
        kind=fc.kind,
        rule_flags=", ".join(rule_tactics) or "none",
        checks=link_checks.checks_for_prompt(checks),
        guidance=_guidance_for_prompt(rules, cleaned),
        content=cleaned[:7000],
        language=prompts.LANGUAGE_NAMES.get(language, "English"),
    )
    try:
        data = get_ollama().chat_json(
            [{"role": "system", "content": prompts.LINK_SYSTEM}, {"role": "user", "content": user}],
            model=model_for(language),
            max_tokens=max(settings.SCAN_MAX_TOKENS, 1100),
        )
        score = max(0, min(100, int(float(data.get("risk_score", 0)))))
    except (LLMUnavailable, TypeError, ValueError) as exc:
        log.info("LLM unavailable for link analysis, using rules and checks only: %s", exc)
        return None

    def clean(s: Any, n: int) -> str:
        s = str(s or "").strip()[:n]
        return "" if output_violates_policy(s) else s

    explanation, _ = sanitize_llm_output(str(data.get("explanation") or "").strip()[:2500], language)
    result = {
        "risk_score": score,
        "verdict": clean(data.get("verdict"), 200),
        "summary": clean(data.get("summary"), 500),
        "tactics": [t for t in _str_list(data.get("tactics"), 10) if t in TACTIC_LABELS],
        "quotes": [q for q in data.get("risky_quotes") or [] if isinstance(q, dict)][:8],
        "claims": [
            {
                "claim": clean(c.get("claim"), 200),
                "assessment": c.get("assessment") if c.get("assessment") in ASSESSMENTS else "unverifiable",
                "why": clean(c.get("why"), 300),
            }
            for c in (data.get("claims") or [])[:5]
            if isinstance(c, dict) and c.get("claim")
        ],
        "red_flags": [
            {"title": clean(f.get("flag"), 120), "detail": "", "evidence": clean(f.get("evidence"), 200), "source": "ai"}
            for f in (data.get("red_flags") or [])[:6]
            if isinstance(f, dict) and f.get("flag")
        ],
        "genuine_signals": [s for s in _str_list(data.get("genuine_signals"), 3, 200) if not output_violates_policy(s)],
        "what_to_do": [s for s in _str_list(data.get("what_to_do"), 4, 200) if not output_violates_policy(s)],
        "explanation": explanation,
    }
    cache_set(key, result)
    return result


def analyze_link(fc: FetchedContent, language: str = "en") -> dict[str, Any]:
    bundle = fc.bundle() or fc.url
    base = analyze_social(bundle, fc.platform, language, use_llm=False)
    cleaned = base["cleaned_text"]
    rules = analyze_rules(cleaned)
    checks = link_checks.run_checks(cleaned, fc)
    fails = sum(1 for c in checks if c["status"] == "fail")
    rule_score = min(100, base["rule_score"] + 12 * fails) if fails else base["rule_score"]
    # a concrete fail (impossible returns, personal UPI collection...) is at least "be careful"
    if fails:
        rule_score = max(rule_score, 45)

    highlights = list(base["highlights"])
    llm = _llm(fc, cleaned, sorted({h["tactic"] for h in highlights}), checks, rules, language) if fc.has_content else None
    if llm:
        lowered = cleaned.lower()
        for q in llm["quotes"]:
            quote, tactic = str(q.get("quote", "")).strip(), q.get("tactic")
            if len(quote) < 4 or tactic not in TACTIC_LABELS or output_violates_policy(str(q.get("why", ""))):
                continue
            idx = lowered.find(quote.lower())
            if idx >= 0 and not any(h["start"] == idx for h in highlights):
                highlights.append(
                    {
                        "start": idx,
                        "end": idx + len(quote),
                        "text": cleaned[idx : idx + len(quote)],
                        "tactic": tactic,
                        "why": str(q.get("why", ""))[:200],
                        "source": "llm",
                    }  # fmt: skip
                )
    highlights.sort(key=lambda h: (h["start"], h["end"]))

    score = _fuse(rule_score, llm["risk_score"] if llm else None)
    level = level_for(score)
    thin = not fc.has_content or len(cleaned) < 60
    if thin and level == "low":
        verdict_key = "unclear"
    else:
        verdict_key = {"critical": "scam", "high": "scam", "medium": "suspicious"}.get(level, "no_signs")
    label, icon = VERDICTS[verdict_key]

    reasons: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        k = item["title"].lower().strip()
        if k and k not in seen:
            seen.add(k)
            reasons.append(item)

    for c in checks:
        if c["status"] == "fail":
            add({"title": c["label"], "detail": c["detail"], "evidence": c.get("evidence", ""), "source": "check"})
    for f in rules.flags:
        add({"title": f.label, "detail": f.reason, "evidence": (f.evidence or [""])[0], "source": "rules"})
    for f in (llm or {}).get("red_flags", []):
        if f["title"]:
            add(f)

    tactics = sorted({h["tactic"] for h in highlights} | set((llm or {}).get("tactics", [])))
    what_to_do = (llm or {}).get("what_to_do") or []
    for step in DEFAULT_STEPS[verdict_key]:
        if len(what_to_do) >= 5:
            break
        if step not in what_to_do:
            what_to_do.append(step)
    explanation = (llm or {}).get("explanation") or base["explanation"]
    summary = (llm or {}).get("summary") or ""
    if not summary:
        summary = (
            f"{PLATFORM_NAMES.get(fc.platform, 'Website')} {fc.kind}"
            + (f" by {fc.author}" if fc.author else "")
            + (f': "{fc.title[:120]}"' if fc.title else "")
            + "."
        )

    return {
        "url": fc.url,
        "final_url": fc.final_url,
        "platform": fc.platform,
        "source": fc.source_info(),
        "fetched": fc.has_content,
        "limitations": list(dict.fromkeys(fc.limitations)),
        "verdict": {
            "key": verdict_key,
            "label": label,
            "icon": icon,
            "headline": (llm or {}).get("verdict") or label,
            "summary": summary,
        },
        "risk_score": score,
        "risk_level": level,
        "tactics": [
            {"key": t, "label": TACTIC_LABELS[t], "count": sum(1 for h in highlights if h["tactic"] == t)} for t in tactics
        ],
        "highlights": highlights,
        "segments": _build_segments(cleaned, highlights),
        "reasons": reasons[:10],
        "claims": (llm or {}).get("claims", []),
        "checks": checks,
        "genuine_signals": (llm or {}).get("genuine_signals", []),
        "what_to_do": what_to_do,
        "explanation": explanation,
        "safe_practices": base["safe_practices"],
        "categories": base["categories"],
        "links": base["links"],
        "rule_score": rule_score,
        "llm_score": llm["risk_score"] if llm else None,
        "llm_used": llm is not None,
        "model": settings.OLLAMA_PRIMARY_MODEL if llm else None,
        "cleaned_text": cleaned,
        "redactions": base["redactions"],
        "official_guidance": [g.id for g in official_guidance.select(_signals(rules), cleaned, level)],
    }
