"""Heuristic link / identifier analysis (no network calls are made to the URLs)."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse

URL_RE = re.compile(
    r"(?:(?:https?://|www\.)[^\s<>\"')\]]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|net|org|xyz|top|club|online|site|live|info|io|co|app|link|click|shop|vip|buzz|icu|cc|tk|ml|ga|cf|gq)(?:/[^\s<>\"')\]]*)?)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b")

SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "rb.gy",
    "cutt.ly",
    "is.gd",
    "shorturl.at",
    "tiny.cc",
    "ow.ly",
    "rebrand.ly",
    "t.ly",
    "s.id",
}
RISKY_TLDS = {
    "xyz",
    "top",
    "club",
    "online",
    "site",
    "live",
    "click",
    "link",
    "shop",
    "vip",
    "buzz",
    "icu",
    "tk",
    "ml",
    "ga",
    "cf",
    "gq",
    "cc",
}
BRANDS = {
    "sbi": "onlinesbi.sbi",
    "hdfc": "hdfcbank.com",
    "icici": "icicibank.com",
    "axis": "axisbank.com",
    "kotak": "kotak.com",
    "paytm": "paytm.com",
    "phonepe": "phonepe.com",
    "sebi": "sebi.gov.in",
    "rbi": "rbi.org.in",
    "npci": "npci.org.in",
    "incometax": "incometax.gov.in",
    "uidai": "uidai.gov.in",
    "zerodha": "zerodha.com",
    "groww": "groww.in",
    "upstox": "upstox.com",
    "amazon": "amazon.in",
    "flipkart": "flipkart.com",
    "indiapost": "indiapost.gov.in",
}
TRUSTED_SUFFIXES = (".gov.in", ".nic.in", ".rbi.org.in", ".sebi.gov.in")
LURE_WORDS = ("kyc", "verify", "update", "secure", "login", "reward", "refund", "bonus", "claim", "support", "helpdesk")


@dataclass
class LinkFinding:
    url: str
    host: str
    issues: list[str]
    score: int


def _host(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    try:
        return (urlparse(url).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def analyze_url(url: str) -> LinkFinding:
    host = _host(url)
    issues: list[str] = []
    score = 0
    if not host:
        return LinkFinding(url, host, ["Malformed link"], 20)
    if host.endswith(TRUSTED_SUFFIXES):
        return LinkFinding(url, host, [], 0)
    try:
        ipaddress.ip_address(host)
        issues.append("Link points to a raw IP address instead of a domain")
        score += 35
    except ValueError:
        pass
    if host in SHORTENERS:
        issues.append("Shortened link hides the real destination")
        score += 20
    if host.startswith("xn--") or ".xn--" in host:
        issues.append("Internationalised (punycode) domain can imitate a real brand")
        score += 30
    tld = host.rsplit(".", 1)[-1]
    if tld in RISKY_TLDS:
        issues.append(f"Uses a low-cost top-level domain (.{tld}) common in scams")
        score += 15
    if url.lower().startswith("http://"):
        issues.append("Not using HTTPS")
        score += 10
    if "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        issues.append("Link contains '@', which can disguise the real destination")
        score += 25
    if host.count("-") >= 2 or len(host) > 40:
        issues.append("Unusually long or hyphenated domain")
        score += 10
    compact = host.replace("-", "").replace(".", "")
    for brand, official in BRANDS.items():
        if brand in compact and not (host == official or host.endswith("." + official)):
            issues.append(f"Mentions '{brand}' but is not the official domain ({official})")
            score += 35
            break
    if any(w in host for w in LURE_WORDS):
        issues.append("Domain contains lure words like 'kyc', 'verify' or 'reward'")
        score += 10
    return LinkFinding(url, host, issues, min(score, 100))


def extract_links(text: str) -> list[LinkFinding]:
    seen: set[str] = set()
    findings = []
    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?")
        if url.lower() in seen:
            continue
        seen.add(url.lower())
        findings.append(analyze_url(url))
    return findings[:20]


def extract_phone_numbers(text: str) -> list[str]:
    return sorted({re.sub(r"[\s-]", "", m.group(0)) for m in PHONE_RE.finditer(text or "")})[:20]
