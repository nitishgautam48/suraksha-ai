"""Download official documents (PDF / HTML) listed in rag/sources.json or requested by an admin.

Guards: HTTPS only, public IP addresses only (no SSRF into the internal network), size cap,
content-type / magic-byte checks, redirects re-validated.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from backend.config import settings
from backend.utils.logging import get_logger

log = get_logger(__name__)
USER_AGENT = "SurakshaAI-KnowledgeFetcher/1.0 (+investor-education indexing)"


class FetchError(Exception):
    pass


@dataclass
class Source:
    url: str
    title: str
    source: str
    topic: str = "general"


def load_manifest(path: Path | None = None) -> list[Source]:
    path = path or settings.KNOWLEDGE_SOURCES_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**{k: d[k] for k in ("url", "title", "source", "topic") if k in d}) for d in data.get("documents", [])]


def _check_public_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise FetchError("Only https:// URLs are allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"Cannot resolve {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError(f"{parsed.hostname} resolves to a non-public address")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "document"


def download(url: str) -> tuple[bytes, str]:
    """Return (content, file_type) where file_type is 'pdf' or 'html'."""
    limit = settings.KNOWLEDGE_MAX_MB * 1024 * 1024
    with httpx.Client(follow_redirects=False, timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(5):  # follow redirects manually so each hop is re-validated
            _check_public_https(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = str(resp.url.join(resp.headers["location"]))
                    continue
                if resp.status_code != 200:
                    raise FetchError(f"HTTP {resp.status_code} for {url}")
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf += chunk
                    if len(buf) > limit:
                        raise FetchError(f"Document exceeds {settings.KNOWLEDGE_MAX_MB} MB")
                ctype = resp.headers.get("content-type", "").lower()
                data = bytes(buf)
                if data.startswith(b"%PDF-") or "application/pdf" in ctype:
                    if not data.startswith(b"%PDF-"):
                        raise FetchError("Server said PDF but content is not a PDF")
                    return data, "pdf"
                if "html" in ctype or data.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
                    return data, "html"
                raise FetchError(f"Unsupported content type: {ctype or 'unknown'}")
        raise FetchError("Too many redirects")


def save_fetched(src: Source, data: bytes, file_type: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{slugify(src.title)}.{file_type}"
    path.write_bytes(data)
    return path
