"""What the regulators say: official SEBI / RBI / NPCI / I4C guidance attached to scan results.

Every entry is a short, fixed paraphrase of public guidance from an Indian authority, with a link to
the official source. Entries are chosen deterministically from the rule-engine signals, never
generated, and they are also handed to the LLM as the *only* regulations it may quote. That
grounds explanations ("SEBI says registered advisers cannot promise returns") without letting the
model invent rules, circular numbers or dates.

Paraphrases, not legal text: the linked official pages are authoritative. Review this file when
the regulators update their guidance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend import i18n


@dataclass(frozen=True)
class Guidance:
    id: str
    authority: str  # who says it (shown as-is in every language)
    source: str  # the official page / document, in English
    url: str
    signals: frozenset[str] = frozenset()  # rule detector keys or risk categories that trigger it
    text: re.Pattern | None = None  # ...or words in the message itself
    needs: frozenset[str] = frozenset()  # and at least one of these signals must also be present


_INVESTMENT = frozenset({"guaranteed_returns", "fake_advisor", "pump_and_dump", "ponzi_scheme"})

GUIDANCE: tuple[Guidance, ...] = (
    Guidance(
        "sebi_no_guarantee",
        "SEBI",
        "SEBI investor education",
        "https://investor.sebi.gov.in/",
        frozenset({"guaranteed_returns", "unrealistic_profits", "pump_language", "fake_success"}),
    ),
    Guidance(
        "sebi_registered",
        "SEBI",
        "SEBI list of recognised intermediaries",
        "https://www.sebi.gov.in/intermediaries.html",
        frozenset({"fake_advisor", "missing_disclosure", "pump_language", "pump_and_dump"}),
    ),
    Guidance(
        "sebi_impersonation",
        "SEBI",
        "sebi.gov.in",
        "https://www.sebi.gov.in/",
        frozenset({"impersonation", "phishing", "credential_request"}),
        text=re.compile(r"\bsebi\b|सेबी", re.I),
        needs=frozenset({"impersonation", "phishing", "credential_request", "payment_request"}),
    ),
    Guidance(
        "sebi_valid_upi",
        "SEBI",
        "SEBI validated UPI handles (@valid) and SEBI Check",
        "https://www.sebi.gov.in/",
        frozenset({"payment_request", "advance_fee"}),
        needs=_INVESTMENT,
    ),
    Guidance(
        "rbi_buds",
        "RBI",
        "RBI Sachet portal",
        "https://sachet.rbi.org.in/",
        frozenset({"ponzi_referral", "ponzi_scheme"}),
    ),
    Guidance(
        "rbi_forex",
        "RBI",
        "RBI Alert List of unauthorised forex trading platforms",
        "https://www.rbi.org.in/",
        text=re.compile(r"\bforex\b|\bfx trading\b|binary option|फॉरेक्स", re.I),
    ),
    Guidance(
        "rbi_never_asks",
        "RBI",
        "RBI Kehta Hai",
        "https://rbikehtahai.rbi.org.in/",
        frozenset({"credential_request", "phishing"}),
    ),
    Guidance(
        "rbi_liability",
        "RBI",
        "RBI customer protection in unauthorised electronic banking transactions (2017)",
        "https://www.rbi.org.in/",
        frozenset({"credential_request", "phishing", "wrong_transfer"}),
    ),
    Guidance(
        "npci_pin",
        "NPCI",
        "UPI safety guidance",
        "https://www.npci.org.in/",
        frozenset({"wrong_transfer", "lottery_prize", "task_scam"}),
    ),
    Guidance(
        "i4c_digital_arrest",
        "I4C, Ministry of Home Affairs",
        "National Cyber Crime Reporting Portal",
        "https://cybercrime.gov.in/",
        frozenset({"digital_arrest"}),
    ),
    Guidance(
        "dot_chakshu",
        "Department of Telecommunications",
        "Sanchar Saathi: Chakshu",
        "https://sancharsaathi.gov.in/",
        frozenset({"impersonation", "lottery_prize", "task_scam", "fear"}),
    ),
)
_BY_ID = {g.id: g for g in GUIDANCE}
# Most specific first: at most three are shown, so a precise rule beats a general one.
PRIORITY = (
    "i4c_digital_arrest",
    "sebi_impersonation",
    "sebi_no_guarantee",
    "rbi_forex",
    "rbi_buds",
    "sebi_registered",
    "rbi_never_asks",
    "npci_pin",
    "sebi_valid_upi",
    "rbi_liability",
    "dot_chakshu",
)
GUIDANCE = tuple(_BY_ID[i] for i in PRIORITY)


def select(signals: set[str] | list[str], text: str = "", risk_level: str = "medium", limit: int = 3) -> list[Guidance]:
    """The most relevant official guidance for these rule signals (detector keys + categories)."""
    if risk_level == "low":
        return []
    sig = set(signals)
    out: list[Guidance] = []
    for g in GUIDANCE:  # in PRIORITY order
        hit = bool(g.signals & sig) or bool(g.text and g.text.search(text or ""))
        if hit and g.text and g.signals and not g.text.search(text or ""):
            hit = False  # entries with both need the words too (e.g. "SEBI" for the SEBI-impersonation note)
        if hit and g.needs and not (g.needs & sig):
            hit = False
        if hit:
            out.append(g)
        if len(out) >= limit:
            break
    return out


def as_payload(items: list[Guidance], language: str = "en") -> list[dict]:
    return [
        {"id": g.id, "authority": g.authority, "source": g.source, "url": g.url, "point": i18n.t(f"og_{g.id}", language)}
        for g in items
    ]


def for_prompt(items: list[Guidance]) -> str:
    """English bullet list for the LLM prompt (the model writes in the user's language itself)."""
    return "\n".join(f"- {g.authority}: {i18n.t(f'og_{g.id}', 'en')}" for g in items) or "none"


def get(guidance_id: str) -> Guidance | None:
    return _BY_ID.get(guidance_id)
