"""Message scanner without copy-paste: a chat screenshot is OCR'd in memory and analysed."""

import io

from PIL import Image

from backend.ocr.tesseract import OCRResult
from backend.services import scan_service


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, "PNG")
    return buf.getvalue()


def test_message_screenshot_is_analysed_and_not_stored(client, auth, monkeypatch, tmp_path):
    h, _ = auth
    seen = {}

    def fake_ocr(data, language=None):
        seen["bytes"] = len(data)
        return OCRResult(text="Dear customer your account will be blocked today. Share OTP 482913 to verify KYC", pages=1,
                         method="tesseract", languages="eng")  # fmt: skip

    monkeypatch.setattr(scan_service, "ocr_image", fake_ocr)
    r = client.post("/analyze/message-image", headers=h, files={"file": ("chat.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen["bytes"] > 0
    assert body["risk_level"] in ("high", "critical")
    assert "482913" not in body["extracted_text"]  # OTP redacted before analysis
    assert body["highlights"] and body["simple_verdict"]
    hist = client.get("/analyze/history", headers=h).json()
    assert hist[0]["source_type"] == "message" and hist[0]["id"] == body["analysis_id"]


def test_message_screenshot_validation(client, auth, monkeypatch):
    h, _ = auth
    r = client.post("/analyze/message-image", headers=h, files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 415
    monkeypatch.setattr(scan_service, "ocr_image", lambda d, language=None: OCRResult("", 1, "tesseract", "eng"))
    r = client.post("/analyze/message-image", headers=h, files={"file": ("blank.png", _png(), "image/png")})
    assert r.status_code == 422
