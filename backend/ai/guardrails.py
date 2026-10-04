"""Compliance guardrails: Suraksha AI never gives investment advice, in any of its 12 languages.

* ``is_advice_request`` catches user questions asking for buy/sell/hold calls, stock picks,
  price predictions, trading signals or broker recommendations, so we answer with an
  educational refusal instead of calling the LLM.
* ``sanitize_llm_output`` scans model output sentence by sentence and removes anything that
  reads like advice or a price prediction (replacing the whole answer if little is left).

Two layers run together: precise English / Hinglish / Hindi regular expressions, and a
multilingual lexicon (``guardrail_lexicon``) that combines product, action, "which/should" and
price-movement words in every supported script. Scam-checking context ("is this a fraud?",
"they promise ...", "verify SEBI registration") is exempt from the lexicon layer so users can
still ask about suspicious offers.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from backend import i18n
from backend.ai import guardrail_lexicon as lex

_ADVICE_REQUEST = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bshould i (buy|sell|hold|invest|exit|book profit|average)\b",
        r"\b(buy|sell|hold)\s+(or|/)\s+(sell|hold|buy)\b",
        r"\bwhich (stock|share|mutual fund|fund|coin|crypto|ipo|etf|broker|scheme)s?\b.{0,30}\b(buy|invest|best|good|choose|pick)\b",
        r"\b(best|top|good)\s+(stock|share|mutual fund|fund|coin|crypto|ipo|etf|broker|trading app)s?\b",
        r"\b(price|target)\s+(prediction|forecast|target)\b",
        r"\btarget\s+price\b",
        r"\b(predict|forecast)\b.{0,30}\b(price|market|nifty|sensex|stock|share|bitcoin)\b",
        r"\bwill\b.{0,30}\b(stock|share|price|nifty|sensex|bitcoin|market)\b.{0,20}\b(go up|rise|fall|crash|increase|decrease|reach)\b",
        r"\b(recommend|suggest)\b.{0,20}\b(stock|share|fund|broker|coin|crypto|ipo)s?\b",
        r"\b(trading|buy|sell|intraday|option)\s+(signal|call|tip)s?\b",
        r"\b(kaunsa|konsa|kon sa)\s+(share|stock|fund)\b",
        r"\b(kharid(u|en|na)|bech(u|en|na))\b.{0,20}\b(share|stock)\b",
        r"(कौन\s*सा|कौनसा)\s*(शेयर|फंड)",
        r"(खरीद|बेच)(ूं|ें|ना)?\s*(या|\?)",
        r"\bशेयर\b.{0,20}\b(खरीद|बेच)",
        r"\b(nifty|sensex|bank nifty|bitcoin|share|stock)\b.{0,30}\b(upar|neeche|niche|badhega|girega)\b",
        r"\btarget\s+(kya|kitna)\b",
    )
)

_ADVICE_OUTPUT = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(you should|i (would )?recommend|i suggest)\s+(buying|selling|holding|investing in|to buy|to sell)\b",
        r"\b(is|looks like)\s+a\s+(good|great|strong)\s+(buy|investment|pick)\b",
        r"\b(strong\s+)?(buy|sell|hold)\s+(rating|recommendation|call)\b",
        r"\btarget price\b",
        r"\b(will|is likely to|is expected to)\s+(rise|go up|fall|crash|double|reach)\b.{0,20}(₹|rs|%|\d)",
        r"\b(entry|exit|stop[- ]?loss)\s+(at|price|level)\b",
    )
)


DISCLAIMER = (
    "Suraksha AI provides scam-awareness and financial-literacy information only. "
    "It does not give investment advice or recommend any security, product or broker."
)


# ---- multilingual lexicon matching ---------------------------------------------------------------
_NUKTAS = dict.fromkeys(map(ord, "\u093c\u09bc\u0a3c\u0abc\u0b3c\u0cbc\u200c\u200d"), None)
_TOKEN = re.compile(r"[\w\u0900-\u0dff&']+")
_SENTENCE = re.compile(r"(?<=[.!?।॥\n])\s*")


def _norm(text: str) -> str:
    """NFC, lower case, no nukta / zero-width joiners, single spaces."""
    text = unicodedata.normalize("NFC", text or "").translate(_NUKTAS).lower()
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


@lru_cache(maxsize=32)
def _compile(entries: tuple[str, ...]) -> tuple[re.Pattern | None, frozenset[str], tuple[str, ...]]:
    """Split a word list into (ASCII regex, exact tokens, substrings)."""
    ascii_parts, tokens, subs = [], set(), []
    for raw in entries:
        prefix = raw.endswith("*")
        word = _norm(raw.rstrip("*"))
        if word.isascii():
            ascii_parts.append(re.escape(word) + ("" if prefix else r"(?![a-z])"))
        elif len(word) <= 2:
            tokens.add(word)
        else:
            subs.append(word)
    rx = re.compile(r"(?<![a-z])(?:" + "|".join(ascii_parts) + ")") if ascii_parts else None
    return rx, frozenset(tokens), tuple(subs)


def _matches(norm_text: str, tokens: set[str], entries: tuple[str, ...]) -> bool:
    rx, exact, subs = _compile(entries)
    return bool((rx and rx.search(norm_text)) or (exact & tokens) or any(s in norm_text for s in subs))


def _prepare(text: str) -> tuple[str, set[str]]:
    norm = _norm(text)
    for phrase in lex.SAFE_PHRASES:
        norm = norm.replace(_norm(phrase), " ")
    return norm, set(_TOKEN.findall(norm))


def _lexicon_request(text: str) -> bool:
    norm, toks = _prepare(text)
    if _matches(norm, toks, lex.EXEMPT):
        return False
    has = lambda words: _matches(norm, toks, words)  # noqa: E731
    question = "?" in norm or "？" in norm
    obj = has(lex.OBJECTS)
    if obj and has(lex.ACTIONS) and (has(lex.ADVICE_MARKERS) or (question and not has(lex.HOW_TO))):
        return True
    if obj and has(lex.BEST):
        return True
    return (obj or has(lex.PRICE)) and has(lex.MOVES) and (question or has(lex.TIME_WORDS) or has(lex.PREDICT_MARKERS))


def _lexicon_output_sentence(sentence: str) -> bool:
    norm, toks = _prepare(sentence)
    has = lambda words: _matches(norm, toks, words)  # noqa: E731
    if has(lex.EXEMPT) or has(lex.NEGATIONS):
        return False
    obj = has(lex.OBJECTS)
    if obj and has(lex.ACTIONS) and has(lex.REC_MARKERS):
        return True
    return (obj or has(lex.PRICE)) and has(lex.MOVES) and (has(lex.TIME_WORDS) or has(lex.PREDICT_MARKERS))


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text or "") if s.strip()]


# ---- public API -----------------------------------------------------------------------------------
def is_advice_request(text: str) -> bool:
    """True for requests for stock picks, buy/sell/hold calls or price predictions (any language)."""
    return any(rx.search(text or "") for rx in _ADVICE_REQUEST) or _lexicon_request(text or "")


def advice_sentences(text: str) -> list[str]:
    """Sentences of model output that read like advice or a price prediction."""
    return [s for s in _sentences(text) if any(rx.search(s) for rx in _ADVICE_OUTPUT) or _lexicon_output_sentence(s)]


def output_violates_policy(text: str) -> bool:
    return any(rx.search(text or "") for rx in _ADVICE_OUTPUT) or bool(advice_sentences(text))


def refusal(language: str = "en") -> str:
    return i18n.t("refusal", language)


def sanitize_llm_output(text: str, language: str = "en") -> tuple[str, bool]:
    """Return (safe_text, was_blocked).

    Advice-like sentences are removed. If they made up much of the answer, the whole answer is
    replaced with the localized refusal; otherwise the refusal is appended so the user knows why.
    """
    bad = advice_sentences(text)
    if not bad:
        return text, False
    kept = [s for s in _sentences(text) if s not in bad]
    remaining = " ".join(s.strip() for s in kept).strip()
    if len(remaining) < 0.5 * len((text or "").strip()) or len(remaining) < 40:
        return refusal(language), True
    return f"{remaining}\n\n{refusal(language)}", True


# Shared with other multilingual keyword matchers (e.g. voice commands).
prepare_text = _prepare
matches_any = _matches
