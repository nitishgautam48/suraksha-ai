"""The 12 languages Suraksha AI serves, and lookups for translated user-facing strings.

Strings live in i18n/strings/<code>.json so native speakers can review them without touching code.
Missing keys fall back to English.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Lang:
    code: str
    name: str  # English name (used in LLM prompts)
    native: str
    tesseract: str  # Tesseract traineddata for the script
    whisper: bool  # Whisper can be told this language explicitly
    speech_tag: str  # BCP-47 tag for browser speech APIs


LANGUAGES: dict[str, Lang] = {
    lang.code: lang
    for lang in (
        Lang("en", "English", "English", "eng", True, "en-IN"),
        Lang("hi", "Hindi", "हिन्दी", "hin", True, "hi-IN"),
        Lang("gu", "Gujarati", "ગુજરાતી", "guj", True, "gu-IN"),
        Lang("mr", "Marathi", "मराठी", "mar", True, "mr-IN"),
        Lang("ta", "Tamil", "தமிழ்", "tam", True, "ta-IN"),
        Lang("bn", "Bengali", "বাংলা", "ben", True, "bn-IN"),
        Lang("te", "Telugu", "తెలుగు", "tel", True, "te-IN"),
        Lang("kn", "Kannada", "ಕನ್ನಡ", "kan", True, "kn-IN"),
        Lang("ml", "Malayalam", "മലയാളം", "mal", True, "ml-IN"),
        Lang("pa", "Punjabi", "ਪੰਜਾਬੀ", "pan", True, "pa-IN"),
        Lang("or", "Odia", "ଓଡ଼ିଆ", "ori", False, "or-IN"),  # Whisper has no Odia: auto-detect
        Lang("as", "Assamese", "অসমীয়া", "asm", True, "as-IN"),
    )
}
CODES = tuple(LANGUAGES)
STRINGS_DIR = Path(__file__).with_name("strings")


@lru_cache
def _strings(code: str) -> dict[str, str]:
    path = STRINGS_DIR / f"{code}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


def t(key: str, language: str | None = "en", **values: object) -> str:
    """Translated string for `key` in `language` (falls back to English), formatted with values."""
    template = _strings(language or "en").get(key) or _strings("en")[key]
    return template.format(**values) if values else template


def name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES["en"]).name


def catalog() -> list[dict]:
    return [
        {
            "code": lang.code,
            "name": lang.name,
            "native": lang.native,
            "speech_tag": lang.speech_tag,
            "voice_input": True,
            "tts": lang.code in ("en", "hi"),
        }
        for lang in LANGUAGES.values()
    ]
