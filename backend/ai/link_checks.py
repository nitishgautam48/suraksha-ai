"""Deterministic checks on a shared post: "does what it claims add up?"

These run before the AI and are handed to it as facts. Each check returns a status:
  fail  - a concrete scam marker (impossible returns, payment to a personal UPI ID, ...)
  warn  - a risk the user should verify (claims SEBI registration: check the number yourself)
  pass  - a reassuring signal (official government domain, SEBI-validated @valid UPI handle)
  info  - context (what could not be checked)
None of these give investment advice; they only test claims against public rules.
"""

from __future__ import annotations

import math
import re
from typing import Any

from backend.ai.link_fetcher import FetchedContent
from backend.ai.url_analysis import TRUSTED_SUFFIXES, analyze_url

SEBI_REG_URL = "https://www.sebi.gov.in/intermediaries.html"

_NUM = r"(\d{1,3}(?:\.\d+)?)"
RATE_RE = re.compile(
    _NUM + r"\s*%\s*(?:profit|return|returns|roi|interest|income|gain|munafa|मुनाफा|रिटर्न)?\s*"
    r"(?:(?:per|a|every|each|har|प्रति)\s*)?"
    r"(day|daily|din|दिन|week|weekly|hafta|हफ्ते|month|monthly|mahina|mahine|महीने|महीना)",
    re.I,
)
PERIODS_PER_YEAR = {
    "day": 365, "daily": 365, "din": 365, "दिन": 365,
    "week": 52, "weekly": 52, "hafta": 52, "हफ्ते": 52,
    "month": 12, "monthly": 12, "mahina": 12, "mahine": 12, "महीने": 12, "महीना": 12,
}  # fmt: skip
DOUBLE_RE = re.compile(
    r"(?:double|doubles|2x|dugna|dogna|दोगुना|डबल)\D{0,30}?(\d{1,3})\s*(din|days?|दिन|weeks?|hafte|months?|mahine|महीने)", re.I
)
_AMT = r"(?:₹|rs\.?\s*|inr\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|hazaar|lakh|lac|lakhs|l|cr|crore|crores)?\b"
GROWTH_RE = re.compile(
    _AMT + r"\s*(?:into|to|se|->|→)\s*" + _AMT + r"\s*(?:in|within|me|mein)\s*(?:just\s*|only\s*)?(\d{1,3})\s*"
    r"(days?|din|weeks?|hafte|months?|mahine|mahino)",
    re.I,
)
UNITS = {
    "k": 1e3,
    "thousand": 1e3,
    "hazaar": 1e3,
    "lakh": 1e5,
    "lac": 1e5,
    "lakhs": 1e5,
    "l": 1e5,
    "cr": 1e7,
    "crore": 1e7,
    "crores": 1e7,
}
SEBI_CLAIM_RE = re.compile(
    r"sebi[\s-]*(?:regd|reg\.?|registered|approved|certified|verified|authori[sz]ed)|registered\s+with\s+sebi|"
    r"सेबी\s*(?:पंजीकृत|रजिस्टर्ड)",
    re.I,
)
SEBI_NO_RE = re.compile(r"\bIN[AHZP]\d{9}\b", re.I)
TIPS_RE = re.compile(
    r"\b(?:target|stop\s?loss|\bsl\b|buy\s+call|sell\s+call|intraday\s+(?:tip|call)s?|jackpot\s+call|multibagger|"
    r"btst|stbt|option\s+tips?|sure\s*shot|accurate\s+calls?|premium\s+calls?)\b",
    re.I,
)
UPI_RE = re.compile(r"\b[\w.\-]{2,64}@(?!gmail|yahoo|outlook|hotmail|icloud|proton)[a-z][a-z0-9]{1,30}\b(?!\.)", re.I)
GROUP_LINK_RE = re.compile(r"(?:chat\.whatsapp\.com/|t\.me/(?:\+|joinchat/)|telegram\.me/(?:\+|joinchat/))", re.I)
DM_RE = re.compile(
    r"\b(?:dm\s+(?:me|now|for)|inbox\s+me|message\s+me|join\s+(?:my|our)\s+(?:vip|premium|telegram|whatsapp))", re.I
)
CELEB_RE = re.compile(
    r"\b(?:mukesh ambani|ratan tata|narayana murthy|nirmala sitharaman|rbi governor|sebi chair(?:man|person)|"
    r"sadhguru|virat kohli|shah rukh khan|amitabh bachchan|elon musk)\b",
    re.I,
)
MONEY_RE = re.compile(r"\b(?:invest|earn|profit|returns?|trading|crypto|deposit|income|kamai|paisa)\b|निवेश|कमाई", re.I)


def _pct(value: float) -> str:
    if value >= 1e7:
        return "more than 1 crore %"
    if value >= 1e5:
        return f"about {value / 1e5:,.1f} lakh %"
    return f"about {value:,.0f}%"


def _returns_math(text: str) -> list[dict[str, Any]]:
    out = []
    for m in RATE_RE.finditer(text):
        rate = float(m.group(1))
        n = PERIODS_PER_YEAR.get(m.group(2).lower())
        if not n or rate <= 0:
            continue
        try:
            annual = (math.pow(1 + rate / 100, n) - 1) * 100
        except OverflowError:
            annual = float("inf")
        if annual <= 30:
            continue
        out.append(
            {
                "key": "returns_math",
                "label": "Promised returns are mathematically unrealistic",
                "status": "fail",
                "detail": f'"{m.group(0).strip()}" compounds to {_pct(annual)} a year. No genuine investment can promise '
                "this; SEBI-registered advisers are not allowed to guarantee any return.",
                "evidence": m.group(0).strip(),
            }
        )
        break
    for m in DOUBLE_RE.finditer(text):
        num, unit = int(m.group(1)), m.group(2).lower()
        days = num * (30 if unit.startswith(("month", "mahine", "महीने")) else 7 if unit.startswith(("week", "hafte")) else 1)
        if days <= 0 or days > 1500:
            continue
        annual = (math.pow(2, 365 / days) - 1) * 100 if days < 3650 else 0
        out.append(
            {
                "key": "doubling",
                "label": '"Money doubles" promise',
                "status": "fail",
                "detail": f"Doubling money in {num} {m.group(2)} equals {_pct(annual)} a year. Bank fixed deposits take "
                "about 10 years to double money; anything this fast is a Ponzi or fraud pattern.",
                "evidence": m.group(0).strip(),
            }
        )
        break
    for m in GROWTH_RE.finditer(text):
        try:
            a = float(m.group(1).replace(",", "")) * UNITS.get((m.group(2) or "").lower(), 1)
            b = float(m.group(3).replace(",", "")) * UNITS.get((m.group(4) or "").lower(), 1)
        except ValueError:
            continue
        unit = m.group(6).lower()
        days = int(m.group(5)) * (30 if unit.startswith(("month", "mahin")) else 7 if unit.startswith(("week", "hafte")) else 1)
        if a <= 0 or b / a < 1.15 or not 0 < days <= 730:
            continue
        try:
            annual = (math.pow(b / a, 365 / days) - 1) * 100
        except OverflowError:
            annual = float("inf")
        if annual <= 100:
            continue
        out.append(
            {
                "key": "growth_claim",
                "label": "Claimed profit is mathematically unrealistic",
                "status": "fail",
                "detail": f'"{m.group(0).strip()}" is {b / a:,.1f} times the money in {m.group(5)} {m.group(6)}, which works out to '
                f"{_pct(annual)} a year. Such screenshots and stories are typically fake and used to sell courses, apps or 'VIP' groups.",
                "evidence": m.group(0).strip(),
            }
        )
        break
    return out


def _sebi(text: str) -> list[dict[str, Any]]:
    claim, number, tips = SEBI_CLAIM_RE.search(text), SEBI_NO_RE.search(text), TIPS_RE.search(text)
    if claim and number:
        return [
            {
                "key": "sebi_number",
                "label": f"Shows a SEBI registration number ({number.group(0).upper()})",
                "status": "warn",
                "detail": "Scammers often copy real registration numbers. Search this number on SEBI's intermediary list "
                "and check that the name, phone and website match exactly before trusting it.",
                "evidence": number.group(0),
                "link": SEBI_REG_URL,
            }
        ]
    if claim:
        return [
            {
                "key": "sebi_claim",
                "label": "Claims to be SEBI-registered but gives no registration number",
                "status": "fail",
                "detail": "Registered investment advisers and research analysts must show their SEBI registration number "
                "(it starts with INA or INH). A claim without a number cannot be verified.",
                "evidence": claim.group(0),
                "link": SEBI_REG_URL,
            }
        ]
    if tips and not number:
        return [
            {
                "key": "unregistered_tips",
                "label": "Gives trading calls without any SEBI registration",
                "status": "warn",
                "detail": "Only SEBI-registered research analysts may give buy/sell calls for a fee. This post shows no "
                "registration number, which is how unregistered 'finfluencers' and pump-and-dump groups operate.",
                "evidence": tips.group(0),
                "link": SEBI_REG_URL,
            }
        ]
    return []


def _payments(text: str) -> list[dict[str, Any]]:
    handles = [h for h in UPI_RE.findall(text) if "." not in h.split("@", 1)[1]]
    if not handles:
        return []
    valid = [h for h in handles if h.split("@", 1)[1].lower().startswith("valid")]
    if valid and len(valid) == len(handles):
        return [
            {
                "key": "upi_valid",
                "label": f"Uses a SEBI-validated '@valid' UPI handle ({valid[0]})",
                "status": "pass",
                "detail": "SEBI-registered intermediaries collect money through '@valid' UPI handles. Still confirm the "
                "name shown in your UPI app matches the registered entity before paying.",
                "evidence": valid[0],
            }
        ]
    return [
        {
            "key": "upi_personal",
            "label": f"Asks for payment to a UPI ID ({handles[0]})",
            "status": "fail",
            "detail": "Genuine brokers and advisers never collect investment money in a personal UPI ID. SEBI-registered "
            "entities use validated '@valid' handles.",
            "evidence": handles[0],
        }
    ]


def _funnel(text: str, fc: FetchedContent) -> list[dict[str, Any]]:
    links = " ".join([fc.url, *fc.outbound_links])
    if fc.kind == "group" or GROUP_LINK_RE.search(links) or GROUP_LINK_RE.search(text) or DM_RE.search(text):
        ev = GROUP_LINK_RE.search(links + " " + text) or DM_RE.search(text)
        return [
            {
                "key": "private_group",
                "label": "Pulls you into a private WhatsApp / Telegram group or DMs",
                "status": "warn",
                "detail": "Moving people into private 'VIP' groups is the usual next step in tips, pump-and-dump and task "
                "scams, because nobody outside can see or report what is promised there.",
                "evidence": ev.group(0) if ev else "",
            }
        ]
    return []


def _celebrity(text: str) -> list[dict[str, Any]]:
    celeb = CELEB_RE.search(text)
    if celeb and MONEY_RE.search(text):
        return [
            {
                "key": "celebrity",
                "label": f"Uses a famous name ({celeb.group(0).title()}) to sell money-making",
                "status": "fail",
                "detail": "Deepfake videos and fake quotes of celebrities and officials are widely used to sell fake "
                "investment apps. Real public figures do not promote such schemes.",
                "evidence": celeb.group(0),
            }
        ]
    return []


def _destination(fc: FetchedContent) -> list[dict[str, Any]]:
    out = []
    targets = [fc.final_url or fc.url, *fc.outbound_links[:5]]
    if fc.redirects:
        hops = [analyze_url(u) for u in fc.redirects]
        if any("Shortened" in i for h in hops for i in h.issues):
            out.append(
                {
                    "key": "shortener",
                    "label": "Shortened link hides where it really goes",
                    "status": "warn",
                    "detail": f"The link actually opens {analyze_url(fc.final_url).host}.",
                    "evidence": fc.redirects[0],
                }
            )
    for url in targets:
        f = analyze_url(url)
        if f.host.endswith(TRUSTED_SUFFIXES):
            out.append({"key": "gov_domain", "label": f"Official government domain ({f.host})", "status": "pass",
                        "detail": "This is a .gov.in / regulator domain.", "evidence": f.host})  # fmt: skip
            break
        if f.score >= 30:
            out.append({"key": "bad_domain", "label": f"Suspicious website: {f.host}", "status": "fail",
                        "detail": "; ".join(f.issues), "evidence": f.host})  # fmt: skip
            break
    return out


def run_checks(text: str, fc: FetchedContent) -> list[dict[str, Any]]:
    checks = [*_returns_math(text), *_sebi(text), *_payments(text), *_funnel(text, fc), *_celebrity(text), *_destination(fc)]
    if fc.limitations:
        checks.append(
            {
                "key": "coverage",
                "label": "Some of this link could not be read",
                "status": "info",
                "detail": " ".join(dict.fromkeys(fc.limitations)),
                "evidence": "",
            }  # fmt: skip
        )
    order = {"fail": 0, "warn": 1, "pass": 2, "info": 3}
    return sorted(checks, key=lambda c: order[c["status"]])


def checks_for_prompt(checks: list[dict[str, Any]]) -> str:
    return "\n".join(f"- [{c['status'].upper()}] {c['label']}: {c['detail']}" for c in checks) or "none"
