"""Remove secrets and identity numbers from user text before it is analysed, stored or logged.

Scam messages often contain the victim's own OTP, card number, Aadhaar or account number. None of
that is needed to judge whether a message is a scam, so it is replaced with a neutral mask (``••••``)
the moment the text arrives. The mask contains no words, so it can never trigger a detector, and
it reads the same in every language. Detection keeps working because the surrounding words
("share your OTP", "card number and CVV") are untouched; the kinds of data hidden are reported
separately as counts.

Kept on purpose: phone numbers, UPI IDs and links. These usually identify the *scammer* and are
what the user needs when reporting to 1930 / cybercrime.gov.in.
"""

from __future__ import annotations

import re

# OTP keywords in English and the Indian scripts (OTP is usually written as a transliteration).
_OTP_WORDS = (
    r"otp|one[ -]?time[ -]?password|verification code|security code|auth(?:entication)? code|code|"
    r"ओटीपी|कोड|ஓடிபி|ওটিপি|ఓటీపీ|ಒಟಿಪಿ|ഒടിപി|ਓਟੀਪੀ|ଓଟିପି|ઓટીપી"
)
_NOT_MONEY = r"(?<!rs)(?<!rs\.)(?<!rs )(?<!rs\. )(?<!₹)(?<!₹ )(?<!inr)(?<!inr )"
_OTP_AFTER = re.compile(rf"(?i)(?:{_OTP_WORDS})[^\d\n]{{0,25}}?{_NOT_MONEY}(?<!\d)(\d{{4,8}})(?!\d)")
# "482913 is your OTP" / "482913 - OTP" (but not "card ending 1234. Do not share this OTP")
_OTP_BEFORE = re.compile(rf"(?i)(?<!\d)(\d{{4,8}})(?!\d)(?=\s*(?:is|as|=|:|-|–)?\s*(?:your|the|aapka|आपका)?\s*(?:{_OTP_WORDS}))")
_PIN = re.compile(r"(?i)\b(?:upi ?pin|m-?pin|atm pin|pin|पिन)\b[^\d\n]{0,15}?(?<!\d)(\d{4,6})(?!\d)")
_CVV = re.compile(r"(?i)\b(?:cvv2?|cvc)\b[^\d\n]{0,10}?(?<!\d)(\d{3,4})(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PAN = re.compile(r"(?i)\b[a-z]{5}\d{4}[a-z]\b")
_ACCOUNT = re.compile(
    r"(?i)(?:a/c|acct|account|acc no|account no|खाता|खाते|अकाउंट|অ্যাকাউন্ট|அக்கவுண்ட்|ఖాతా|ಖಾತೆ|അക്കൗണ്ട്|ਖਾਤਾ|ଖାତା|ખાતા)"
    r"[^\d\n]{0,20}?(?<!\d)(\d{9,18})(?!\d)"
)
_PASSWORD = re.compile(r"(?i)\b(?:password|passcode|pwd|पासवर्ड)\s*(?:is|:|=|-)\s*(\S{4,})")
MASK = "••••"
_PHONE_91 = re.compile(r"^(?:91)?[6-9]\d{9}$")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return (redacted_text, {kind: count}) with only non-zero counts."""
    counts: dict[str, int] = {}

    def bump(kind: str) -> None:
        counts[kind] = counts.get(kind, 0) + 1

    def group_sub(rx: re.Pattern, kind: str, label: str, s: str) -> str:
        def repl(m: re.Match) -> str:
            bump(kind)
            a, b = m.span(1)
            return m.group(0)[: a - m.start()] + label + m.group(0)[b - m.start() :]

        return rx.sub(repl, s)

    def card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits) and not _PHONE_91.match(digits):
            bump("card")
            return MASK
        return m.group(0)

    def aadhaar(m: re.Match) -> str:
        raw = m.group(0)
        if _PHONE_91.match(raw):  # +91 mobile written without separators
            return raw
        bump("aadhaar")
        return MASK

    def pan(m: re.Match) -> str:
        bump("pan")
        return MASK

    out = text or ""
    out = group_sub(_PASSWORD, "password", MASK, out)
    out = group_sub(_CVV, "cvv", MASK, out)
    out = group_sub(_PIN, "pin", MASK, out)
    out = group_sub(_ACCOUNT, "account", MASK, out)
    out = _CARD.sub(card, out)
    out = _AADHAAR.sub(aadhaar, out)
    out = _PAN.sub(pan, out)
    out = group_sub(_OTP_AFTER, "otp", MASK, out)
    out = group_sub(_OTP_BEFORE, "otp", MASK, out)
    return out, counts
