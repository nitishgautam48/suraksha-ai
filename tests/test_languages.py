import json
import string
from pathlib import Path

import pytest

from backend import i18n

STRINGS = Path(i18n.__file__).with_name("strings")


def test_twelve_languages_match_prototype():
    names = [lang.name for lang in i18n.LANGUAGES.values()]
    assert names == [
        "English",
        "Hindi",
        "Gujarati",
        "Marathi",
        "Tamil",
        "Bengali",
        "Telugu",
        "Kannada",
        "Malayalam",
        "Punjabi",
        "Odia",
        "Assamese",
    ]


@pytest.mark.parametrize("code", i18n.CODES)
def test_every_language_has_every_key_with_same_placeholders(code):
    en = json.loads((STRINGS / "en.json").read_text())
    other = json.loads((STRINGS / f"{code}.json").read_text())
    en.pop("_meta"), other.pop("_meta")
    assert set(other) == set(en), set(en) ^ set(other)
    for key, text in en.items():
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
        assert fields(other[key]) == fields(text), (code, key)
        assert ("1930" in text) <= ("1930" in other[key]), (code, key)  # helpline never dropped


def test_fallback_to_english():
    assert i18n.t("verdict_low", "xx") == "Looks safe"


def test_languages_endpoint(client):
    langs = client.get("/languages").json()
    assert len(langs) == 12 and {lang["code"] for lang in langs} >= {"ta", "or", "as"}
    assert next(lang for lang in langs if lang["code"] == "ta")["speech_tag"] == "ta-IN"


def test_tamil_user_gets_tamil_verdict_and_sms(client, register, sms_outbox):
    import uuid

    data = register(f"ta-{uuid.uuid4().hex[:6]}@example.com")
    h = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.patch("/auth/me", headers=h, json={"language": "ta"}).json()["language"] == "ta"
    r = client.post("/analyze/message", headers=h, json={"message_text": "Share your OTP now to claim your prize"}).json()
    assert r["simple_verdict"]["headline"] in {i18n.t(f"verdict_{lvl}", "ta") for lvl in ("medium", "high", "critical")}
    assert r["explanation"].startswith(i18n.t(f"level_{r['risk_level']}", "ta")[:10])
    client.post("/auth/phone/request-otp", json={"phone": "9820144199", "language": "bn"})
    assert "Suraksha AI" in sms_outbox[-1]["text"] and "কোড" in sms_outbox[-1]["text"]


def test_ocr_language_selection(monkeypatch):
    from backend.ocr import tesseract

    monkeypatch.setattr(tesseract, "installed_languages", lambda: frozenset({"eng", "hin", "tam", "ben"}))
    assert tesseract.available_languages("ta") == "eng+hin+tam"
    assert tesseract.available_languages("ml") == "eng+hin"  # pack not installed -> skipped
    assert tesseract.available_languages(None) == "eng+hin"


def test_lesson_translation_cached(client, register, monkeypatch):
    import uuid

    from backend.services import learning_service

    calls = []

    class FakeLLM:
        def chat_json(self, messages, model=None, **kw):
            calls.append(model)
            return {"title": "UPI பாதுகாப்பு", "content": "உங்கள் UPI PIN-ஐ ஒருபோதும் பகிர வேண்டாம். 1930"}

    monkeypatch.setattr(learning_service, "get_ollama", lambda: FakeLLM())
    h = {"Authorization": "Bearer " + register(f"tr-{uuid.uuid4().hex[:6]}@example.com")["access_token"]}
    course = client.get("/learning/courses", headers=h).json()[0]
    lesson_id = client.get(f"/learning/courses/{course['id']}", headers=h).json()["lessons"][0]["id"]
    en = client.get(f"/learning/lessons/{lesson_id}", headers=h).json()
    assert en["language"] == "en" and not en["translated"]
    ta = client.get(f"/learning/lessons/{lesson_id}?language=ta", headers=h).json()
    assert ta["translated"] and ta["title"] == "UPI பாதுகாப்பு"
    client.get(f"/learning/lessons/{lesson_id}?language=ta", headers=h)
    assert len(calls) == 1  # stored after the first translation
