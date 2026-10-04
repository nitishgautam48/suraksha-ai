"""Privacy by design (redaction, upload deletion) and uncertainty on every result."""

import io

import pytest
from PIL import Image

from backend.utils.redact import MASK, redact

SECRET_CASES = [
    ("Your OTP is 482913, do not share", "482913", "otp"),
    ("482913 is your one time password", "482913", "otp"),
    ("आपका ओटीपी 556677 है", "556677", "otp"),
    ("card 4111 1111 1111 1111 exp 12/27", "4111 1111 1111 1111", "card"),
    ("CVV 123 required", "123", "cvv"),
    ("enter UPI PIN 4567 to receive", "4567", "pin"),
    ("Aadhaar 2345 6789 0123 verify", "2345 6789 0123", "aadhaar"),
    ("PAN ABCDE1234F blocked", "ABCDE1234F", "pan"),
    ("a/c no 123456789012 frozen", "123456789012", "account"),
    ("खाता 98765432109 बंद", "98765432109", "account"),
    ("password: Hunter2024", "Hunter2024", "password"),
]


@pytest.mark.parametrize(("text", "secret", "kind"), SECRET_CASES)
def test_secrets_are_masked(text, secret, kind):
    out, counts = redact(text)
    assert secret not in out and MASK in out
    assert counts.get(kind) == 1


def test_scam_evidence_is_kept():
    text = "Pay Rs 2,499 to win@ybl or call +91 9876543210 / 919876543210, link https://bit.ly/x on card ending 1234"
    out, counts = redact(text)
    assert out == text and counts == {}


def test_message_analysis_never_stores_or_returns_secrets(client, auth):
    h, _ = auth
    msg = "Dear customer your KYC expired. Share OTP 482913 and card 4111 1111 1111 1111 CVV 123 to avoid block"
    r = client.post("/analyze/message", headers=h, json={"message_text": msg})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["privacy"]["redacted"] == {"otp": 1, "card": 1, "cvv": 1}
    assert body["privacy"]["note"]
    assert "482913" not in r.text and "4111" not in r.text

    from backend.database.session import SessionLocal
    from backend.models import ScamAnalysis

    with SessionLocal() as db:
        row = db.get(ScamAnalysis, __import__("uuid").UUID(body["analysis_id"]))
        assert "482913" not in row.input_excerpt and "4111" not in row.input_excerpt
        assert MASK in row.input_excerpt


def test_chat_history_stores_redacted_question(client, auth):
    h, _ = auth
    client.post("/chat", headers=h, json={"message": "someone asked my OTP 778899, what to do?"})
    hist = client.get("/chat/history", headers=h).json()
    blob = str(hist)
    assert "778899" not in blob


def test_uploaded_screenshot_deleted_after_text_extraction(client, auth, monkeypatch):
    from backend.ocr.tesseract import OCRResult

    monkeypatch.setattr(
        "backend.services.scan_service.ocr_image",
        lambda data, language=None: OCRResult("Guaranteed returns! Share OTP 123456 now", 1, "tesseract", "eng"),
    )
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    h, _ = auth
    r = client.post("/scan/image", headers=h, files={"file": ("s.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "123456" not in (body["extracted_text"] or "")

    from pathlib import Path

    from backend.database.session import SessionLocal
    from backend.models import UploadedFile

    with SessionLocal() as db:
        f = db.get(UploadedFile, __import__("uuid").UUID(body["file_id"]))
        assert f.deleted_at is not None
        assert not Path(f.file_path).exists()


def test_every_result_states_confidence_and_where_to_verify(client, auth):
    h, _ = auth
    r = client.post(
        "/analyze/message",
        headers=h,
        json={"message_text": "Hi", "language": "hi"},
    ).json()
    conf = r["confidence"]
    assert conf["level"] in ("low", "medium", "high")
    assert "short_text" in conf["reasons"]
    assert "1930" in conf["note"]
    assert any(v.get("tel") == "tel:1930" for v in conf["verify"])
    assert any("cybercrime.gov.in" in (v.get("url") or "") for v in conf["verify"])


def test_confidence_drops_when_rules_and_ai_disagree():
    from backend.ai.confidence import assess

    base = {"cleaned_text": "x" * 200, "warning_flags": [{}] * 3, "llm_used": True}
    agree = assess({**base, "rule_score": 90, "llm_score": 92, "risk_score": 92})
    disagree = assess({**base, "rule_score": 90, "llm_score": 20, "risk_score": 90})
    rules_only = assess({**base, "rule_score": 90, "llm_score": None, "risk_score": 90, "llm_used": False})
    assert agree["level"] == "high" and "strong_signals" in agree["reasons"]
    assert disagree["level"] == "low" and "signals_disagree" in disagree["reasons"]
    assert rules_only["level"] == "medium" and "ai_unavailable" in rules_only["reasons"]


def test_confidence_low_for_unsupported_script_without_ai():
    from backend.ai.confidence import assess

    r = assess(
        {"cleaned_text": "இது ஒரு நீண்ட செய்தி " * 5, "warning_flags": [], "llm_used": False, "rule_score": 0, "risk_score": 0},
        "ta",
    )
    assert r["level"] == "low" and "language_limited" in r["reasons"]
    assert r["note"] != assess({"cleaned_text": "x" * 100, "rule_score": 0, "risk_score": 0}, "en")["note"]


SCAM = (
    "Invest Rs 5000 today and earn Rs 500 daily guaranteed. Only 20 slots left! Share OTP 482913 and pay to wealthking@ybl now."
)


@pytest.mark.parametrize("kind", ["text", "message", "social"])
def test_quick_preview_is_instant_unsaved_and_never_safer_than_full(client, auth, kind):
    h, _ = auth
    before = client.get("/analyze/history", headers=h).json()
    q = client.post("/scan/quick", json={"text": SCAM, "kind": kind, "language": "en"}, headers=h)
    assert q.status_code == 200, q.text
    q = q.json()
    assert q["preliminary"] is True and q["analysis_id"] is None
    assert q["engine"]["llm_used"] is False and q["risk_level"] != "low"
    assert "482913" not in str(q) and q["privacy"]["redacted"] == {"otp": 1}
    assert client.get("/analyze/history", headers=h).json() == before  # nothing stored

    full = {
        "text": lambda: client.post("/scan/text", json={"text": SCAM, "language": "en"}, headers=h),
        "message": lambda: client.post("/analyze/message", json={"message_text": SCAM, "language": "en"}, headers=h),
        "social": lambda: client.post("/analyze/social", json={"text": SCAM, "platform": "other", "language": "en"}, headers=h),
    }[kind]().json()
    assert full["risk_score"] >= q["risk_score"]


def test_quick_preview_requires_login(client):
    assert client.post("/scan/quick", json={"text": SCAM}).status_code == 401


def test_scan_answer_is_capped(monkeypatch):
    from backend.ai import analyzer
    from backend.config import settings

    seen = {}

    class Fake:
        def chat_json(self, messages, model=None, **kw):
            seen.update(kw)
            return {"risk_score": 80, "categories": [], "reasons": [], "safe_practices": [], "explanation": "Scam."}

    monkeypatch.setattr(analyzer, "get_ollama", lambda: Fake())
    monkeypatch.setattr(analyzer, "cache_get", lambda k: None)
    analyzer.analyze_content("Guaranteed 10% monthly returns, send money now", language="en")
    assert seen["max_tokens"] == settings.SCAN_MAX_TOKENS
