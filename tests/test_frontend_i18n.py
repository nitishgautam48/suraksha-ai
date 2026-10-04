"""The web app's Hindi dictionary must stay consistent with the English interface strings."""

import json
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
CORE = [
    "Dashboard", "Scan message", "Get Help", "Report this scam", "How sure are we?", "Family Readiness",
    "Say a command", "Your privacy", "Settings", "Log out", "Send OTP", "Call 1930",
    "This is an automated estimate and it can be wrong. Before you pay or share anything, check with your bank's official number or call 1930.",
]  # fmt: skip


def _dict(code: str) -> dict:
    d = json.loads((FRONTEND / "i18n" / f"{code}.json").read_text(encoding="utf-8"))
    d.pop("_meta", None)
    return d


def test_hindi_dictionary_has_core_strings_and_keeps_placeholders():
    hi = _dict("hi")
    assert len(hi) > 700
    for key in CORE:
        assert hi.get(key) and hi[key] != key, key
    for key, value in hi.items():
        assert set(re.findall(r"\{\d\}", key)) == set(re.findall(r"\{\d\}", value)), key
        assert value.strip(), key


def test_core_strings_still_exist_in_the_app():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for key in CORE:
        assert key.replace("'", "\\'") in html or key in html, key


def test_interface_languages_are_hindi_and_english():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "const LANGS=['English','Hindi'];" in html
    assert sorted(p.stem for p in (FRONTEND / "i18n").glob("*.json")) == ["hi"]
