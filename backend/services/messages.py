"""Short user-facing texts (SMS, verdicts, reports) - translations live in backend/i18n/strings."""

from __future__ import annotations

from backend import i18n


def text(key: str, language: str, **values: object) -> str:
    return i18n.t(key, language, **values)
