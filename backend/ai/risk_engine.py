"""Deterministic rule engine: detects manipulation signals and produces an explainable score."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.ai.patterns import (
    DETECTORS,
    GENERAL_PRACTICES,
    RISK_CATEGORIES,
    SAFE_CONTEXT,
    SAFE_PRACTICES,
    Detector,
)
from backend.ai.url_analysis import LinkFinding, extract_links, extract_phone_numbers
from backend.config import settings


@dataclass
class Span:
    start: int
    end: int
    text: str
    detector: str
    label: str
    category: str


@dataclass
class Flag:
    key: str
    label: str
    category: str
    reason: str
    weight: int
    evidence: list[str] = field(default_factory=list)


@dataclass
class RuleResult:
    score: int
    flags: list[Flag]
    spans: list[Span]
    links: list[LinkFinding]
    phone_numbers: list[str]
    safe_context: bool

    @property
    def categories(self) -> list[str]:
        return sorted({f.category for f in self.flags} | ({"phishing"} if self.risky_links else set()))

    @property
    def risky_links(self) -> list[LinkFinding]:
        return [link for link in self.links if link.score >= 25]

    def reasons(self) -> list[str]:
        out = [f.reason for f in sorted(self.flags, key=lambda f: -f.weight)]
        for link in self.risky_links:
            out.append(f"Suspicious link {link.host}: {'; '.join(link.issues)}")
        return out


def level_for(score: int) -> str:
    if score >= settings.RISK_CRITICAL_THRESHOLD:
        return "critical"
    if score >= settings.RISK_HIGH_THRESHOLD:
        return "high"
    if score >= settings.RISK_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


_NEGATION = re.compile(r"(\bnever|\bnot|\bdon'?t|\bdo not|\bno one|\bnobody|\bmat)\W+(\w+\W+){0,3}$", re.IGNORECASE)


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATION.search(text[max(0, start - 30) : start]))


def _match_detector(det: Detector, text: str) -> list[Span]:
    spans = []
    for rx in det.compiled:
        for m in rx.finditer(text):
            if m.end() <= m.start() or (det.negatable and _negated(text, m.start())):
                continue
            spans.append(Span(m.start(), m.end(), m.group(0), det.key, det.label, det.category))
    return spans


def _merge_spans(spans: list[Span]) -> list[Span]:
    """Drop spans fully contained in a longer span of the same detector; sort by position."""
    spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    kept: list[Span] = []
    for s in spans:
        if any(k.detector == s.detector and k.start <= s.start and k.end >= s.end for k in kept):
            continue
        kept.append(s)
    return kept


def analyze_rules(text: str) -> RuleResult:
    text = text or ""
    flags: list[Flag] = []
    all_spans: list[Span] = []
    for det in DETECTORS:
        spans = _match_detector(det, text)
        if not spans:
            continue
        all_spans.extend(spans)
        evidence = list(dict.fromkeys(s.text.strip() for s in spans))[:3]
        flags.append(Flag(det.key, det.label, det.category, det.reason, det.weight, evidence))

    # "missing_disclosure" only matters when there is an actual investment pitch.
    keys = {f.key for f in flags}
    if "missing_disclosure" in keys and not keys & {
        "guaranteed_returns",
        "unrealistic_profits",
        "fake_advisor",
        "pump_language",
        "ponzi_referral",
    }:
        flags = [f for f in flags if f.key != "missing_disclosure"]
        all_spans = [s for s in all_spans if s.detector != "missing_disclosure"]

    links = extract_links(text)
    safe_hits = sum(bool(rx.search(text)) for rx in SAFE_CONTEXT)
    safe_context = safe_hits > 0

    # Combine independent signals with diminishing returns: 1 - prod(1 - w).
    remaining = 1.0
    for f in flags:
        bonus = min(len(f.evidence) - 1, 2) * 3  # repeated evidence nudges weight up slightly
        remaining *= 1 - min(f.weight + bonus, 90) / 100
    for link in links:
        remaining *= 1 - min(link.score, 90) / 100
    score = round((1 - remaining) * 100)
    if len({f.category for f in flags}) >= 3:
        score = max(score, 70)  # several distinct manipulation categories together
    if safe_hits:
        # Awareness content quotes scam phrases; dampen strongly when several warning cues co-occur.
        score = round(score * (0.5 if safe_hits == 1 else 0.25))

    return RuleResult(
        score=max(0, min(score, 100)),
        flags=flags,
        spans=_merge_spans(all_spans),
        links=links,
        phone_numbers=extract_phone_numbers(text),
        safe_context=safe_context,
    )


def safe_practices_for(categories: list[str], limit: int = 6) -> list[str]:
    out: list[str] = []
    for cat in categories:
        for tip in SAFE_PRACTICES.get(cat, []):
            if tip not in out:
                out.append(tip)
    if not out:
        out.append("Even when a message looks safe, never share OTPs, PINs or passwords.")
    out = out[: limit - len(GENERAL_PRACTICES)] if len(out) > limit - len(GENERAL_PRACTICES) else out
    return out + GENERAL_PRACTICES


def category_label(key: str) -> str:
    return RISK_CATEGORIES.get(key, key.replace("_", " ").title())
