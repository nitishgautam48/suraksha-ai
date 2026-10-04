import pytest

from backend.ai.analyzer import analyze_content, analyze_social
from backend.ai.risk_engine import analyze_rules, level_for
from backend.ai.url_analysis import analyze_url

SCAMS = [
    "Guaranteed 5% daily returns! Double your money in 30 days. Only 3 slots left, join now.",
    "Your PAN card KYC expired. Share OTP to avoid account suspension.",
    "Congratulations! You won KBC lottery Rs 25 lakh. Pay processing fee Rs 5000 to claim.",
    "Mom I lost my phone, this is my new number. Emergency, please send Rs 20000 via GPay urgently",
    "आपका खाता ब्लॉक हो जाएगा, तुरंत ओटीपी बताएं",
    "Refer 5 friends and earn level income daily. Binary plan with guaranteed payout.",
]
BENIGN = [
    "Hi beta, dinner at 8 tonight? Bring the vegetables please.",
    "Dear customer, SBI never asks for OTP. Never share your OTP with anyone. Beware of fraud calls.",
    "Your electricity bill is due on the 5th. Pay via the official app.",
    "Do not click on unknown links. Report fraud at 1930.",
]


@pytest.mark.parametrize("text", SCAMS)
def test_scams_score_high(text):
    r = analyze_rules(text)
    assert level_for(r.score) in ("high", "critical"), (r.score, [f.key for f in r.flags])


@pytest.mark.parametrize("text", BENIGN)
def test_benign_scores_low(text):
    r = analyze_rules(text)
    assert level_for(r.score) == "low", (r.score, [f.key for f in r.flags])


def test_levels():
    assert [level_for(s) for s in (0, 24, 25, 49, 50, 74, 75, 100)] == [
        "low",
        "low",
        "medium",
        "medium",
        "high",
        "high",
        "critical",
        "critical",
    ]


def test_lookalike_domain_flagged():
    finding = analyze_url("http://sbi-kyc-update.xyz/login")
    assert finding.score >= 50
    assert any("official domain" in i for i in finding.issues)


def test_official_domains_clean():
    assert analyze_url("https://www.sebi.gov.in").score == 0
    assert analyze_url("https://onlinesbi.sbi/").score == 0


def test_analyze_content_output_shape_without_llm():
    r = analyze_content(SCAMS[0], language="hi").to_dict()
    assert r["llm_used"] is False
    assert {"risk_level", "risk_score", "reasons", "safe_practices"} <= r.keys()
    assert r["safe_practices"] and r["reasons"]
    assert "guaranteed_returns" in r["categories"]


def test_social_segments_reconstruct_text():
    text = "Hidden gem multibagger to the moon 🚀🚀🚀 I turned 10k to 5 lakh. Only 20 seats left. Trust me!"
    r = analyze_social(text, "telegram")
    assert "".join(s["text"] for s in r["segments"]) == r["cleaned_text"]
    keys = {t["key"] for t in r["tactics"]}
    assert {"pump_language", "fake_success_stories", "scarcity", "emotional_manipulation"} <= keys
    for h in r["highlights"]:
        assert r["cleaned_text"][h["start"] : h["end"]] == h["text"]
