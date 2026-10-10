"""Link checker: URL handling, SSRF protection, platform readers (with recorded page fixtures, no
network), claim checks and the /analyze/link endpoint."""

import json

import pytest

from backend.ai import link_checks, link_fetcher
from backend.ai.link_fetcher import FetchedContent, FetchError

TG_CHANNEL = """<html><head><meta property="og:title" content="Stock Market King VIP"></head><body>
<div class="tgme_channel_info_header_title"><span>Stock Market King VIP</span></div>
<div class="tgme_channel_info_description">SEBI registered expert &#128200; 100% sure shot intraday calls.
Join premium: t.me/+AbCdEf123</div>
<div class="tgme_channel_info_counter"><span class="counter_value">48.2K</span> <span class="counter_type">subscribers</span></div>
<div class="tgme_widget_message_text">Today's jackpot call: BUY now, target 3% daily profit guaranteed! Only 10 seats left.</div>
<div class="tgme_widget_message_text">Pay Rs 4999 for lifetime VIP to kingtrader@ybl and send screenshot.</div>
</body></html>"""

TG_POST = """<div class="tgme_widget_message_owner_name"><span>Crypto Guru</span></div>
<div class="tgme_widget_message_text js-message_text">Double your money in 30 days<br>Message me on WhatsApp</div>"""

X_OEMBED = json.dumps(
    {
        "author_name": "RBI",
        "html": '<blockquote class="twitter-tweet"><p lang="en" dir="ltr">RBI never asks for your OTP or PIN. '
        'Report fraud at <a href="https://t.co/x">cybercrime.gov.in</a></p>&mdash; RBI (@RBI) '
        '<a href="https://twitter.com/RBI/status/1">March 1, 2026</a></blockquote>',
    }
)

IG_PAGE = """<html><head><title>Instagram</title>
<meta property="og:title" content="Rich Trader on Instagram" />
<meta property="og:description" content="12K likes, 340 comments - richtrader_official on March 3, 2026: &quot;I turned 10,000 into 5 lakh in 2 weeks with this app! Link in bio, limited slots &#x1f680;&quot;" />
</head><body>login</body></html>"""

VTT = """WEBVTT
Kind: captions
Language: hi

00:00:00.000 --> 00:00:02.000
<c>guaranteed</c> profit every month

00:00:02.000 --> 00:00:04.000
guaranteed profit every month

00:00:04.000 --> 00:00:06.000
join my telegram channel now
"""


@pytest.fixture
def fake_web(monkeypatch):
    """Route link_fetcher.safe_get to canned responses keyed by URL substring."""
    pages: dict[str, tuple[str, str]] = {}

    def fake(url, headers=None, max_bytes=None, timeout=None):
        for key, (body, ctype) in pages.items():
            if key in url:
                return url, body, ctype, []
        raise FetchError("The website could not be reached.")

    monkeypatch.setattr(link_fetcher, "safe_get", fake)
    monkeypatch.setattr(link_fetcher, "_ydl_info", lambda url: None)
    return pages


# ---- URL handling -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "url", "platform"),
    [
        ("https://www.instagram.com/reel/Cxyz123/", "https://www.instagram.com/reel/Cxyz123/", "instagram"),
        ("check this out youtu.be/abc123 pls", "https://youtu.be/abc123", "youtube"),
        ("t.me/s/stockking", "https://t.me/s/stockking", "telegram"),
        ("https://x.com/someone/status/12345", "https://x.com/someone/status/12345", "x"),
        ("https://chat.whatsapp.com/AbCd", "https://chat.whatsapp.com/AbCd", "whatsapp"),
        ("http://sebi-kyc-update.top/login", "http://sebi-kyc-update.top/login", "other"),
    ],
)
def test_normalise_and_detect(raw, url, platform):
    assert link_fetcher.normalise_url(raw) == url
    assert link_fetcher.detect_platform(url) == platform


@pytest.mark.parametrize("raw", ["", "hello there", "ftp://example.com/x", "javascript:alert(1)"])
def test_rejects_non_links(raw):
    with pytest.raises(FetchError):
        link_fetcher.normalise_url(raw)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/", "http://localhost/admin", "http://10.1.2.3/", "http://169.254.169.254/latest/meta-data"]
)
def test_ssrf_private_addresses_blocked(url):
    with pytest.raises(FetchError, match="private"):
        link_fetcher.safe_get(url)


def test_unusual_port_blocked():
    with pytest.raises(FetchError, match="port"):
        link_fetcher.safe_get("http://example.com:8080/")


# ---- platform readers ---------------------------------------------------------------------------
def test_telegram_channel(fake_web):
    fake_web["t.me/s/stockking"] = (TG_CHANNEL, "text/html")
    fc = link_fetcher.fetch_link("https://t.me/stockking")
    assert fc.kind == "channel" and fc.title == "Stock Market King VIP"
    assert "sure shot" in fc.caption and "jackpot call" in fc.page_text
    assert fc.extra["Channel size"].startswith("48.2K")
    assert "2 recent posts" in fc.parts


def test_telegram_post(fake_web):
    fake_web["t.me/cryptoguru/77?embed=1"] = (TG_POST, "text/html")
    fc = link_fetcher.fetch_link("https://t.me/cryptoguru/77")
    assert fc.kind == "post" and fc.author == "Crypto Guru"
    assert "Double your money in 30 days" in fc.caption


def test_x_post(fake_web):
    fake_web["publish.twitter.com/oembed"] = (X_OEMBED, "application/json")
    fc = link_fetcher.fetch_link("https://x.com/RBI/status/1")
    assert "never asks for your OTP" in fc.caption
    assert fc.author.startswith("RBI")


def test_instagram_caption_from_page(fake_web):
    fake_web["instagram.com/reel/abc"] = (IG_PAGE, "text/html")
    fc = link_fetcher.fetch_link("https://www.instagram.com/reel/abc/")
    assert fc.kind == "video" and fc.author == "@richtrader_official"
    assert fc.caption.startswith("I turned 10,000 into 5 lakh")
    assert any("audio" in limitation for limitation in fc.limitations)


def test_instagram_login_wall(fake_web):
    fake_web["instagram.com/p/locked"] = ("<html><head><title>Instagram</title></head></html>", "text/html")
    fc = link_fetcher.fetch_link("https://www.instagram.com/p/locked/")
    assert not fc.has_content
    assert any("logging in" in limitation for limitation in fc.limitations)


def test_youtube_with_subtitles(fake_web, monkeypatch):
    info = {
        "title": "Earn 1 lakh monthly from trading",
        "uploader": "Money Guru",
        "upload_date": "20260301",
        "duration": 95,
        "description": "Join my VIP group https://t.me/+vip123",
        "automatic_captions": {"hi": [{"ext": "vtt", "url": "https://captions.example/abc.vtt"}]},
        "webpage_url": "https://www.youtube.com/watch?v=abc",
    }
    monkeypatch.setattr(link_fetcher, "_ydl_info", lambda url: info)
    fake_web["captions.example"] = (VTT, "text/vtt")
    fc = link_fetcher.fetch_link("https://youtu.be/abc", "hi")
    assert fc.kind == "video" and fc.published == "01-03-2026"
    assert fc.transcript == "guaranteed profit every month join my telegram channel now"
    assert fc.transcript_source == "subtitles"
    assert "https://t.me/+vip123" in fc.outbound_links


def test_whatsapp_chat_link():
    fc = link_fetcher.fetch_link("https://wa.me/919876543210?text=I%20want%20the%20VIP%20tips")
    assert fc.extra["Opens a chat with"] == "+919876543210"
    assert fc.caption == "I want the VIP tips"


def test_unreachable_site_reports_limitation(fake_web):
    fc = link_fetcher.fetch_link("https://nothing-here.example/")
    assert not fc.has_content and fc.limitations


# ---- claim checks -------------------------------------------------------------------------------
def _fc(**kw):
    kw.setdefault("url", "https://example.com/post")
    kw.setdefault("final_url", kw["url"])
    return FetchedContent(platform="other", **kw)


def _keys(text, fc=None):
    return {c["key"]: c["status"] for c in link_checks.run_checks(text, fc or _fc())}


def test_returns_math():
    checks = link_checks.run_checks("Earn 3% daily profit, withdraw anytime", _fc())
    c = next(c for c in checks if c["key"] == "returns_math")
    assert c["status"] == "fail" and "lakh %" in c["detail"]
    assert "returns_math" not in _keys("FD rates are 7% per year")
    assert "doubling" in _keys("Your money will double in 30 days")


def test_sebi_checks():
    assert _keys("SEBI registered advisor, join now")["sebi_claim"] == "fail"
    assert _keys("SEBI registered RA INH000012345")["sebi_number"] == "warn"
    assert _keys("Nifty buy call target 22500 stop loss 22300")["unregistered_tips"] == "warn"
    assert "sebi_claim" not in _keys("Learn how SEBI protects investors")


def test_payment_checks():
    assert _keys("Pay the fee to rajtips@ybl now")["upi_personal"] == "fail"
    assert _keys("Pay via upi abc.brk@validhdfc")["upi_valid"] == "pass"
    assert "upi_personal" not in _keys("Email us at help@company.com")


def test_funnel_and_celebrity():
    assert _keys("DM me for the VIP group")["private_group"] == "warn"
    assert _keys("hello", _fc(outbound_links=["https://t.me/+abc"]))["private_group"] == "warn"
    assert _keys("Mukesh Ambani reveals how to earn 50000 daily")["celebrity"] == "fail"
    assert "celebrity" not in _keys("Mukesh Ambani spoke at the company AGM")


def test_destination_checks():
    assert _keys("x", _fc(url="https://www.sebi.gov.in/x"))["gov_domain"] == "pass"
    fc = FetchedContent(
        url="https://bit.ly/x", final_url="http://sbi-kyc-verify.top/", platform="other", redirects=["https://bit.ly/x"]
    )
    keys = _keys("x", fc)
    assert keys["shortener"] == "warn" and keys["bad_domain"] == "fail"


# ---- endpoint -----------------------------------------------------------------------------------
def test_link_endpoint_scam_channel(client, auth, fake_web):
    h, _ = auth
    fake_web["t.me/s/stockking"] = (TG_CHANNEL, "text/html")
    r = client.post("/analyze/link", headers=h, json={"url": "https://t.me/stockking"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["platform"] == "telegram" and body["fetched"]
    assert body["verdict"]["key"] == "scam"
    assert body["risk_level"] in ("high", "critical")
    statuses = {c["key"]: c["status"] for c in body["checks"]}
    assert statuses["returns_math"] == "fail" and statuses["upi_personal"] == "fail"
    assert statuses["sebi_claim"] == "fail" and statuses["private_group"] == "warn"
    assert any(x["source"] == "check" for x in body["reasons"])
    assert body["what_to_do"] and body["source"]["title"] == "Stock Market King VIP"
    hist = client.get("/analyze/history", headers=h).json()
    assert hist[0]["source_type"] == "link" and hist[0]["platform"] == "telegram"


def test_link_endpoint_genuine_post(client, auth, fake_web):
    h, _ = auth
    fake_web["publish.twitter.com/oembed"] = (X_OEMBED, "application/json")
    body = client.post("/analyze/link", headers=h, json={"url": "https://x.com/RBI/status/1"}).json()
    assert body["verdict"]["key"] == "no_signs"
    assert body["risk_level"] == "low"


def test_link_endpoint_unreadable_and_invalid(client, auth, fake_web):
    h, _ = auth
    body = client.post("/analyze/link", headers=h, json={"url": "https://nothing-here.example/"}).json()
    assert body["verdict"]["key"] == "unclear" and body["limitations"]
    r = client.post("/analyze/link", headers=h, json={"url": "just some words"})
    assert r.status_code == 422


def test_link_ai_reasoning_is_used_and_filtered(client, auth, fake_web, monkeypatch):
    """With the local AI on, its claims / red flags / steps reach the user; advice sentences are dropped
    and the AI can never lower the rules score."""
    from backend.ai import link_analyzer

    class FakeLLM:
        def chat_json(self, messages, model=None, **kw):
            assert "Automatic checks" in messages[1]["content"] and "[FAIL]" in messages[1]["content"]
            return {
                "risk_score": 10,
                "verdict": "This is a tips-selling scam channel.",
                "summary": "It sells paid 'VIP' trading calls and asks for UPI payment.",
                "tactics": ["guaranteed_returns", "scarcity"],
                "risky_quotes": [{"quote": "lifetime VIP", "tactic": "fomo", "why": "paid group upsell"}],
                "claims": [{"claim": "3% daily profit guaranteed", "assessment": "false", "why": "No investment can do this."}],
                "red_flags": [{"flag": "Paid VIP group", "evidence": "lifetime VIP"}],
                "genuine_signals": [],
                "what_to_do": ["Do not pay the VIP fee.", "You should buy Reliance shares instead."],
                "explanation": "The channel promises impossible returns. You should buy Nifty futures now. Report it.",
            }

    monkeypatch.setattr(link_analyzer, "get_ollama", lambda: FakeLLM())
    fake_web["t.me/s/stockking"] = (TG_CHANNEL, "text/html")
    body = client.post("/analyze/link", headers=auth[0], json={"url": "https://t.me/stockking"}).json()
    assert body["engine"]["llm_used"] and body["risk_score"] >= body["engine"]["rule_score"]
    assert body["claims"][0]["assessment"] == "false"
    assert any(r["source"] == "ai" and r["title"] == "Paid VIP group" for r in body["reasons"])
    assert "Do not pay the VIP fee." in body["what_to_do"]
    assert not any("Reliance" in s for s in body["what_to_do"])
    assert "Nifty futures" not in body["explanation"]
    assert any(h["source"] == "llm" and h["tactic"] == "fomo" for h in body["highlights"])


def test_growth_claim_math():
    checks = link_checks.run_checks("I turned 10,000 into 5 lakh in 2 weeks with this app! Link in bio", _fc())
    c = next(c for c in checks if c["key"] == "growth_claim")
    assert c["status"] == "fail" and "50.0 times" in c["detail"]
    assert "growth_claim" not in _keys("My SIP grew from 1 lakh to 1.1 lakh in 12 months")
    assert "growth_claim" in _keys("Rs 5k se 50k in 10 din, guaranteed")
