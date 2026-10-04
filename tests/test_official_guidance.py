"""Official SEBI / RBI / NPCI / I4C guidance on results and in the LLM prompt."""

import json
from pathlib import Path

import pytest

from backend import i18n
from backend.ai import analyzer, official_guidance
from backend.ai.guardrails import output_violates_policy

CASES = [
    ("Invest Rs 5000 today and earn Rs 500 daily guaranteed. Add 3 friends to unlock bonus.", "sebi_no_guarantee"),
    (
        "Dear Investor, your Demat will be suspended. Update KYC at sebi-kyc.in, share the OTP with our SEBI officer.",
        "sebi_impersonation",
    ),
    ("Sir I sent 3000 by mistake to your Paytm, please send it back, approve the request.", "npci_pin"),
    ("This is CBI. You are under digital arrest, stay on video call and transfer money now.", "i4c_digital_arrest"),
    ("Join our forex trading app, fixed 4% daily profit, capital safe.", "rbi_forex"),
    ("हमारी योजना में निवेश करें, हर महीने 10% पक्का मुनाफा। कोई जोखिम नहीं।", "sebi_no_guarantee"),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_relevant_guidance_is_attached(text, expected):
    r = analyzer.analyze_content(text, language="en", use_llm=False)
    assert expected in r.official_guidance
    assert 1 <= len(r.official_guidance) <= 3


def test_genuine_messages_get_no_guidance():
    r = analyzer.analyze_content("Bank alert: Rs 2,500 debited from A/c XX4521 towards electricity bill.", use_llm=False)
    assert r.risk_level == "low" and r.official_guidance == []


def test_every_entry_is_translated_official_and_never_advice():
    for g in official_guidance.GUIDANCE:
        assert g.url.startswith("https://") and (".gov.in" in g.url or ".org.in" in g.url), g.url
        for lang in i18n.LANGUAGES:
            text = i18n.t(f"og_{g.id}", lang)
            assert text and not output_violates_policy(text), (g.id, lang)
    assert len(official_guidance.PRIORITY) == len(set(official_guidance.PRIORITY)) == len(official_guidance._BY_ID)


def test_llm_may_only_cite_the_listed_guidance(monkeypatch):
    seen = {}

    class Fake:
        def chat_json(self, messages, model=None, **kw):
            seen["system"], seen["user"] = messages[0]["content"], messages[1]["content"]
            return {"risk_score": 90, "categories": [], "reasons": [], "safe_practices": [], "explanation": "Scam."}

    monkeypatch.setattr(analyzer, "get_ollama", lambda: Fake())
    monkeypatch.setattr(analyzer, "cache_get", lambda k: None)
    analyzer.analyze_content(CASES[0][0], language="hi")
    assert "Cite ONLY the official guidance listed" in seen["system"]
    assert "SEBI: " + i18n.t("og_sebi_no_guarantee", "en") in seen["user"]


def test_api_returns_localized_guidance_with_sources(client, auth):
    h, _ = auth
    r = client.post("/analyze/message", json={"message_text": CASES[0][0], "language": "hi"}, headers=h).json()
    og = r["official_guidance"]
    assert og and og[0]["authority"] == "SEBI" and og[0]["url"].startswith("https://")
    assert og[0]["point"] == i18n.t(f"og_{og[0]['id']}", "hi")
    q = client.post("/scan/quick", json={"text": CASES[0][0], "kind": "text"}, headers=h).json()
    assert [g["id"] for g in q["official_guidance"]] == [g["id"] for g in og]


def test_chat_knowledge_base_has_the_same_guidance():
    kb = Path(__file__).resolve().parent.parent / "backend/rag/knowledge/09_official_guidance_quick_reference.md"
    text = kb.read_text(encoding="utf-8")
    for g in official_guidance.GUIDANCE:
        assert i18n.t(f"og_{g.id}", "en") in text and g.url in text


def test_frontend_strings_translated():
    hi = json.loads((Path(__file__).resolve().parent.parent / "frontend/i18n/hi.json").read_text(encoding="utf-8"))
    for s in ("What the regulators say", "Report fraud: 1930", "Safety lessons"):
        assert s in hi
