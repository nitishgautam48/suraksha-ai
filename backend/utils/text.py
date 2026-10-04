"""Text cleaning helpers used before risk detection and LLM analysis."""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")
_WHATSAPP_TS = re.compile(
    r"^\s*\[?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\]?\s*[-–]?\s*",
    re.IGNORECASE | re.MULTILINE,
)
_MULTI_WS = re.compile(r"[ \t\f\v]+")
_MULTI_NL = re.compile(r"\n{3,}")


def clean_text(text: str, max_chars: int = 20000) -> str:
    """Normalise unicode, strip invisible characters / chat timestamps, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _WHATSAPP_TS.sub("", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = _MULTI_WS.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()[:max_chars]


def excerpt(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
