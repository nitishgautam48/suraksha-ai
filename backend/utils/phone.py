"""Phone number normalisation to E.164 (Indian 10-digit mobiles by default)."""

from __future__ import annotations

import re

from backend.config import settings

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")


class InvalidPhone(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """'98201 44120', '+91-98201-44120', '0919820144120' -> '+919820144120'."""
    s = re.sub(r"[\s\-().]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        if not _E164.match(s):
            raise InvalidPhone("Enter a valid phone number with country code")
        if s.startswith("+91") and not _INDIAN_MOBILE.match(s[3:]):
            raise InvalidPhone("Enter a valid 10-digit Indian mobile number")
        return s
    s = s.lstrip("0")
    if settings.DEFAULT_COUNTRY_CODE == "91":
        if s.startswith("91") and len(s) == 12:
            s = s[2:]
        if not _INDIAN_MOBILE.match(s):
            raise InvalidPhone("Enter a valid 10-digit mobile number")
    elif not s.isdigit() or not 6 <= len(s) <= 14:
        raise InvalidPhone("Enter a valid phone number")
    return f"+{settings.DEFAULT_COUNTRY_CODE}{s}"


def mask_phone(phone: str) -> str:
    return phone[:3] + "*" * max(len(phone) - 7, 0) + phone[-4:] if phone else ""
