"""Voice navigation commands in all 12 languages."""

import pytest

from backend.voice.commands import parse_command

CASES = [
    ("en", "check this message", "scan"), ("en", "I need help", "help"), ("en", "read the screen", "read"),
    ("hinglish", "message check karo", "scan"), ("hinglish", "madad chahiye", "help"),
    ("hi", "संदेश की जाँच करो", "scan"), ("hi", "मदद करो", "help"), ("hi", "पढ़कर सुनाओ", "read"),
    ("mr", "मेसेज तपासा", "scan"), ("mr", "मदत करा", "help"),
    ("gu", "સંદેશ તપાસો", "scan"), ("gu", "મદદ કરો", "help"),
    ("ta", "இந்த செய்தியை சரிபார்", "scan"), ("ta", "உதவி வேண்டும்", "help"),
    ("bn", "এই বার্তা যাচাই করো", "scan"), ("bn", "সাহায্য চাই", "help"),
    ("te", "ఈ సందేశం తనిఖీ చేయి", "scan"), ("te", "సహాయం కావాలి", "help"),
    ("kn", "ಈ ಸಂದೇಶ ಪರಿಶೀಲಿಸಿ", "scan"), ("kn", "ಸಹಾಯ ಬೇಕು", "help"),
    ("ml", "ഈ സന്ദേശം പരിശോധിക്കൂ", "scan"), ("ml", "സഹായം വേണം", "help"),
    ("pa", "ਇਹ ਸੁਨੇਹਾ ਜਾਂਚੋ", "scan"), ("pa", "ਮਦਦ ਕਰੋ", "help"),
    ("or", "ଏହି ବାର୍ତ୍ତା ଯାଞ୍ଚ କର", "scan"), ("or", "ସାହାଯ୍ୟ ଦରକାର", "help"),
    ("as", "এই বাৰ্তা পৰীক্ষা কৰক", "scan"), ("as", "সহায় লাগে", "help"),
    ("hi", "शिकायत दर्ज करनी है", "report"), ("ta", "குடும்ப உறுப்பினர்கள்", "family"),
    ("en", "stop", "stop"), ("hi", "रुको", "stop"), ("en", "go home", "home"),
]  # fmt: skip


@pytest.mark.parametrize(("lang", "phrase", "intent"), CASES, ids=[f"{c[0]}-{c[2]}-{i}" for i, c in enumerate(CASES)])
def test_commands(lang, phrase, intent):
    assert parse_command(phrase) == intent


def test_unknown_phrase():
    assert parse_command("the weather is nice") is None


def test_command_endpoint_text(client, auth):
    h, _ = auth
    r = client.post("/voice/command", headers=h, data={"text": "मदद करो"})
    assert r.status_code == 200 and r.json()["intent"] == "help"
    assert client.post("/voice/command", headers=h).status_code == 422


def test_tts_endpoint_returns_wav(client, auth, monkeypatch):
    from backend.voice import tts

    monkeypatch.setattr(tts, "synthesize", lambda text, language: b"RIFF....WAVEfmt fake")
    h, _ = auth
    r = client.post("/voice/tts", json={"text": "नमस्ते, यह एक परीक्षण है।", "language": "hi"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content.startswith(b"RIFF")


def test_tts_endpoint_reports_unavailable(client, auth, monkeypatch):
    from backend.voice import tts

    def boom(text, language):
        raise tts.TTSUnavailable("TTS disabled")

    monkeypatch.setattr(tts, "synthesize", boom)
    h, _ = auth
    assert client.post("/voice/tts", json={"text": "hello", "language": "en"}, headers=h).status_code == 503
    assert client.post("/voice/tts", json={"text": "வணக்கம்", "language": "ta"}, headers=h).status_code == 422
    assert client.post("/voice/tts", json={"text": "hello"}).status_code == 401


def test_tts_status(client, auth, monkeypatch):
    from backend.voice import tts

    h, _ = auth
    monkeypatch.setattr(tts, "available", lambda: False)
    assert client.get("/voice/tts", headers=h).json() == {"available": False, "languages": []}
    monkeypatch.setattr(tts, "available", lambda: True)
    assert {"en", "hi"} <= set(client.get("/voice/tts", headers=h).json()["languages"])
