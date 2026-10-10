"""Open a shared link and pull out the words a scam would use.

Supports Instagram reels/posts, YouTube videos/shorts, Telegram posts and channels, X (Twitter) posts,
Facebook and WhatsApp invite pages, and any ordinary web page. For each link we collect the title,
author, caption or description, the spoken words of a video (subtitles, or a local Whisper
transcript when voice is installed) and the visible page text.

Safety: links come from users, so every request goes through `safe_get`, which only allows
http(s) on the standard ports, refuses private / loopback / link-local addresses (no SSRF into the
server's own network), re-checks every redirect hop, and caps time and size. Nothing here logs in to
any platform: if a platform hides a post behind a login, we say so instead of working around it.
"""

from __future__ import annotations

import html as html_lib
import importlib.util
import ipaddress
import json
import os
import re
import socket
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx

from backend.config import settings
from backend.utils.logging import get_logger

log = get_logger(__name__)

URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+/[^\s<>\"']*", re.I)

PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "instagram": ("instagram.com", "instagr.am"),
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "telegram": ("t.me", "telegram.me", "telegram.dog"),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
    "whatsapp": ("chat.whatsapp.com", "wa.me", "whatsapp.com"),
}
PLATFORM_NAMES = {
    "instagram": "Instagram",
    "youtube": "YouTube",
    "telegram": "Telegram",
    "x": "X (Twitter)",
    "facebook": "Facebook",
    "whatsapp": "WhatsApp",
    "other": "Website",
}


class FetchError(Exception):
    """The link could not be opened (blocked, private, too large, timed out...). Message is user-facing."""


@dataclass
class FetchedContent:
    url: str
    final_url: str
    platform: str
    kind: str = "page"  # video | post | channel | group | page
    title: str = ""
    author: str = ""
    published: str = ""
    caption: str = ""
    transcript: str = ""
    page_text: str = ""
    extra: dict[str, str] = field(default_factory=dict)  # e.g. subscribers, group name
    outbound_links: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)  # what we managed to read: caption, transcript, ...
    limitations: list[str] = field(default_factory=list)
    duration: int | None = None
    transcript_source: str | None = None  # subtitles | whisper

    @property
    def has_content(self) -> bool:
        return bool((self.caption + self.transcript + self.page_text + self.title).strip())

    def bundle(self, max_chars: int = 12000) -> str:
        """Labelled text that the rules engine and the AI read."""
        sections = [
            ("Title", self.title),
            ("Posted by", self.author),
            *[(k, v) for k, v in self.extra.items() if v],
            ("Caption / description", self.caption),
            ("Spoken in the video", self.transcript),
            ("Text on the page", self.page_text),
            ("Links in the post", "\n".join(self.outbound_links[:10])),
        ]
        out = "\n\n".join(f"{label}:\n{value.strip()}" for label, value in sections if value and value.strip())
        return out[:max_chars]

    def source_info(self) -> dict[str, Any]:
        return {
            "title": self.title[:300],
            "author": self.author[:120],
            "published": self.published[:40],
            "kind": self.kind,
            "platform_name": PLATFORM_NAMES.get(self.platform, "Website"),
            "parts": self.parts,
            "duration_seconds": self.duration,
            "transcript_source": self.transcript_source,
            "characters": len(self.bundle()),
            "redirects": self.redirects[:5],
            "extra": {k: v[:120] for k, v in self.extra.items()},
        }


# ---- URL handling -------------------------------------------------------------------------------
def normalise_url(raw: str) -> str:
    """Take whatever the user pasted ("check this https://..." or a bare domain) and return one URL."""
    raw = (raw or "").strip()
    scheme = re.match(r"^([a-z][a-z0-9+.-]*):", raw, re.I)
    if scheme and scheme.group(1).lower() not in ("http", "https"):
        raise FetchError("Only web links (http or https) can be checked.")
    m = URL_IN_TEXT.search(raw)
    url = (m.group(0) if m else raw).strip().rstrip(".,;:!?)\"'")
    if not url:
        raise FetchError("Paste a link to check.")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        raise FetchError("That doesn't look like a web link. Paste the full link, e.g. https://www.instagram.com/reel/...")
    return url


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return platform
    return "other"


def _check_host(host: str, port: int | None) -> None:
    if port not in (None, 80, 443):
        raise FetchError("Links to unusual ports are not opened for safety.")
    try:
        infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError("This website could not be found. The link may be fake or already taken down.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError("This link points to a private network address, so it was not opened.")


def safe_get(
    url: str, *, headers: dict[str, str] | None = None, max_bytes: int | None = None, timeout: float | None = None
) -> tuple[str, str, str, list[str]]:
    """GET a public URL safely. Returns (final_url, text, content_type, redirect_chain)."""
    max_bytes = max_bytes or settings.LINK_MAX_BYTES
    timeout = timeout or settings.LINK_FETCH_TIMEOUT
    hdrs = {
        "User-Agent": settings.LINK_USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
        **(headers or {}),
    }
    chain: list[str] = []
    current = url
    with httpx.Client(follow_redirects=False, timeout=timeout, headers=hdrs) as client:
        for _ in range(6):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise FetchError("The link redirected to something that is not a web page.")
            _check_host(parsed.hostname, parsed.port)
            try:
                with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        chain.append(current)
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if resp.status_code == 404 or resp.status_code == 410:
                        raise FetchError("This post or page no longer exists (it may have been deleted or reported).")
                    if resp.status_code >= 400:
                        raise FetchError(f"The website refused the request (HTTP {resp.status_code}).")
                    body = b""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) > max_bytes:
                            body = body[:max_bytes]
                            break
                    ctype = resp.headers.get("content-type", "")
                    text = body.decode(resp.encoding or "utf-8", errors="replace")
                    return current, text, ctype, chain
            except httpx.TimeoutException as exc:
                raise FetchError("The website took too long to answer.") from exc
            except httpx.HTTPError as exc:
                raise FetchError("The website could not be reached.") from exc
    raise FetchError("The link redirected too many times.")


# ---- HTML parsing -------------------------------------------------------------------------------
class _PageParser(HTMLParser):
    """Collects <title>, <meta>, visible text, links, and text inside elements with chosen classes."""

    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, base_url: str = "", classes: tuple[str, ...] = ()):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.classes = classes
        self.meta: dict[str, str] = {}
        self.title = ""
        self.text: list[str] = []
        self.links: list[str] = []
        self.by_class: dict[str, list[str]] = {c: [] for c in classes}
        self._skip = 0
        self._in_title = False
        self._stack: list[tuple[str, str | None]] = []  # (tag, class being captured)
        self._buf: dict[int, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
            return
        if tag == "br":
            self._data("\n")
            return
        if tag in self.VOID:
            return
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and a.get("href", "").startswith(("http://", "https://", "/")):
            href = urljoin(self.base_url, a["href"]) if self.base_url else a["href"]
            if href.startswith("http") and href not in self.links:
                self.links.append(href)
        cls = a.get("class", "").split()
        hit = next((c for c in self.classes if c in cls), None)
        self._stack.append((tag, hit))
        if hit:
            self._buf[len(self._stack)] = []

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        # pop to the matching tag (tolerates sloppy HTML)
        for depth in range(len(self._stack), 0, -1):
            if self._stack[depth - 1][0] == tag:
                for d in range(len(self._stack), depth - 1, -1):
                    hit = self._stack[d - 1][1]
                    if hit and d in self._buf:
                        text = _squash("".join(self._buf.pop(d)))
                        if text:
                            self.by_class[hit].append(text)
                del self._stack[depth - 1 :]
                break
        if tag in ("p", "div", "li", "h1", "h2", "h3", "section", "article", "tr"):
            self._data("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        self._data(data)

    def _data(self, data: str) -> None:
        for buf in self._buf.values():
            buf.append(data)
        if not self._skip:
            self.text.append(data)

    def visible_text(self, limit: int = 6000) -> str:
        lines = [_squash(line) for line in "".join(self.text).splitlines()]
        out, seen = [], set()
        for line in lines:
            if len(line) < 2 or line in seen:
                continue
            seen.add(line)
            out.append(line)
        return "\n".join(out)[:limit]


def _squash(s: str) -> str:
    return re.sub(r"[ \t ]+", " ", s).strip()


def parse_page(html: str, base_url: str = "", classes: tuple[str, ...] = ()) -> _PageParser:
    p = _PageParser(base_url, classes)
    try:
        p.feed(html)
        p.close()
    except Exception as exc:  # malformed HTML: keep what we have
        log.debug("HTML parse issue: %s", exc)
    return p


def _meta_description(p: _PageParser) -> str:
    return p.meta.get("og:description") or p.meta.get("twitter:description") or p.meta.get("description") or ""


def _meta_title(p: _PageParser) -> str:
    return p.meta.get("og:title") or p.meta.get("twitter:title") or _squash(p.title)


def _external_links(links: list[str], own_host: str) -> list[str]:
    out = []
    for link in links:
        host = (urlparse(link).hostname or "").lower()
        if host and not (host == own_host or host.endswith("." + own_host) or own_host.endswith("." + host)):
            out.append(link)
    return out[:20]


# ---- platform readers ---------------------------------------------------------------------------
def fetch_link(raw_url: str, language: str = "en") -> FetchedContent:
    url = normalise_url(raw_url)
    platform = detect_platform(url)
    fc = FetchedContent(url=url, final_url=url, platform=platform)
    readers = {
        "youtube": _read_youtube,
        "instagram": _read_instagram,
        "telegram": _read_telegram,
        "x": _read_x,
        "facebook": _read_generic,
        "whatsapp": _read_whatsapp,
        "other": _read_generic,
    }
    try:
        readers[platform](fc, language)
    except FetchError as exc:
        fc.limitations.append(str(exc))
    if not fc.has_content and not fc.limitations:
        fc.limitations.append("We could not read any text from this link.")
    return fc


def _read_generic(fc: FetchedContent, language: str = "en") -> None:
    final, body, ctype, chain = safe_get(fc.url)
    fc.final_url, fc.redirects = final, chain
    if "html" not in ctype and "text" not in ctype:
        fc.limitations.append("The link opens a file, not a web page, so only the link itself was checked.")
        return
    p = parse_page(body, final)
    fc.title = _meta_title(p)
    desc = _meta_description(p)
    if desc:
        fc.caption = desc
        fc.parts.append("description")
    fc.page_text = p.visible_text()
    if fc.page_text:
        fc.parts.append("page text")
    fc.outbound_links = _external_links(p.links, (urlparse(final).hostname or "").lower())
    if fc.platform == "facebook" and not desc:
        fc.limitations.append("Facebook shows this post only to logged-in users, so little text could be read.")


def _ydl_info(url: str) -> dict[str, Any] | None:
    """Metadata via yt-dlp (no download, no login). None if yt-dlp is missing or the site refuses."""
    if importlib.util.find_spec("yt_dlp") is None:
        return None
    import yt_dlp  # type: ignore[import-not-found]

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": settings.LINK_FETCH_TIMEOUT,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as exc:  # yt-dlp raises many types; any failure just means "no metadata"
        log.info("yt-dlp could not read %s: %s", urlparse(url).hostname, str(exc)[:200])
        return None


def _apply_ydl(fc: FetchedContent, info: dict[str, Any], language: str) -> None:
    fc.kind = "video" if info.get("duration") else "post"
    fc.title = (info.get("title") or "").strip()
    fc.author = (info.get("uploader") or info.get("channel") or info.get("uploader_id") or "").strip()
    if info.get("upload_date"):
        d = str(info["upload_date"])
        fc.published = f"{d[6:8]}-{d[4:6]}-{d[:4]}" if len(d) == 8 else d
    fc.duration = int(info["duration"]) if info.get("duration") else None
    desc = (info.get("description") or "").strip()
    if desc:
        fc.caption = desc[:6000]
        fc.parts.append("caption" if fc.platform == "instagram" else "description")
    if info.get("channel_follower_count"):
        fc.extra["Followers"] = f"{int(info['channel_follower_count']):,}"
    subs = _subtitle_text(info, language)
    if subs:
        fc.transcript, fc.transcript_source = subs, "subtitles"
        fc.parts.append("spoken words (subtitles)")
    fc.outbound_links = [m.group(0) for m in URL_IN_TEXT.finditer(desc)][:10]


def _subtitle_text(info: dict[str, Any], language: str) -> str:
    tracks: dict[str, list[dict[str, Any]]] = {**(info.get("automatic_captions") or {}), **(info.get("subtitles") or {})}
    if not tracks:
        return ""
    for lang in (language, "hi", "en", *tracks.keys()):
        for key in (lang, f"{lang}-IN", f"{lang}-orig"):
            fmts = tracks.get(key) or []
            vtt = next((f for f in fmts if f.get("ext") == "vtt" and f.get("url")), None)
            if vtt:
                try:
                    _, body, _, _ = safe_get(vtt["url"], max_bytes=600_000)
                except FetchError:
                    return ""
                return vtt_to_text(body)[:8000]
    return ""


def vtt_to_text(vtt: str) -> str:
    """WebVTT -> plain text. Auto-captions repeat each line as it scrolls; keep each line once."""
    out: list[str] = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit() or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        line = _squash(html_lib.unescape(re.sub(r"<[^>]+>", "", line)))
        if line and (not out or out[-1] != line):
            out.append(line)
    deduped: list[str] = []
    for line in out:
        if line not in deduped[-3:]:
            deduped.append(line)
    return " ".join(deduped)


def _maybe_transcribe(fc: FetchedContent, language: str) -> None:
    """Spoken words via local Whisper when there are no subtitles (voice build only, short videos only)."""
    if fc.transcript or fc.kind != "video":
        return
    if not (settings.LINK_TRANSCRIBE and settings.VOICE_ENABLED):
        return
    if importlib.util.find_spec("whisper") is None or importlib.util.find_spec("yt_dlp") is None:
        fc.limitations.append("The video's spoken words were not checked (voice features are not installed on this server).")
        return
    if fc.duration and fc.duration > settings.LINK_MAX_MEDIA_SECONDS:
        fc.limitations.append(
            f"The video is longer than {settings.LINK_MAX_MEDIA_SECONDS // 60} minutes, so only its text was checked, not its audio."
        )
        return
    import yt_dlp  # type: ignore[import-not-found]

    from backend.voice import stt

    with tempfile.TemporaryDirectory(prefix="suraksha-link-") as tmp:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio[filesize<25M]/bestaudio/worst",
            "max_filesize": 25 * 1024 * 1024,
            "outtmpl": os.path.join(tmp, "audio.%(ext)s"),
            "socket_timeout": settings.LINK_FETCH_TIMEOUT,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([fc.final_url or fc.url])
            files = [f for f in os.listdir(tmp) if f.startswith("audio.")]
            if not files:
                raise FetchError("no audio")
            path = os.path.join(tmp, files[0])
            with open(path, "rb") as fh:
                audio = fh.read()
            result = stt.transcribe(audio, suffix=os.path.splitext(path)[1] or ".m4a", language=language)
        except Exception as exc:  # download blocked, no audio track, Whisper error...
            log.info("Could not transcribe %s: %s", urlparse(fc.url).hostname, str(exc)[:200])
            fc.limitations.append("We could not listen to the video's audio; only its text was checked.")
            return
    if result.text:
        fc.transcript, fc.transcript_source = result.text[:8000], "whisper"
        fc.parts.append("spoken words (AI transcript)")


def _read_youtube(fc: FetchedContent, language: str) -> None:
    info = _ydl_info(fc.url)
    if info:
        _apply_ydl(fc, info, language)
        fc.final_url = info.get("webpage_url") or fc.url
    else:
        # oEmbed gives the title and channel without any API key; the page gives the description.
        try:
            _, body, _, _ = safe_get(f"https://www.youtube.com/oembed?format=json&url={quote(fc.url, safe='')}")
            data = json.loads(body)
            fc.title, fc.author = data.get("title", ""), data.get("author_name", "")
        except (FetchError, ValueError):
            pass
        try:
            _read_generic(fc, language)
        except FetchError as exc:
            if not fc.title:
                raise
            fc.limitations.append(str(exc))
        fc.kind = "video"
        fc.page_text = ""  # YouTube's page text is menus and recommendations, not the video
        if "page text" in fc.parts:
            fc.parts.remove("page text")
    _maybe_transcribe(fc, language)


def _read_instagram(fc: FetchedContent, language: str) -> None:
    path = urlparse(fc.url).path
    fc.kind = "video" if re.search(r"/(reels?|tv)/", path) else "post" if "/p/" in path else "page"
    info = _ydl_info(fc.url)
    if info:
        _apply_ydl(fc, info, language)
        _maybe_transcribe(fc, language)
        return
    try:
        final, body, _, chain = safe_get(fc.url)
    except FetchError as exc:
        fc.limitations.append(f"{exc} Instagram often hides posts from anyone not logged in.")
        return
    fc.final_url, fc.redirects = final, chain
    p = parse_page(body, final)
    desc = _meta_description(p)
    title = _meta_title(p)
    if "login" in final or not (desc or title) or title.strip().lower() in ("instagram", "login • instagram"):
        fc.limitations.append(
            "Instagram didn't let us read this post without logging in. Paste the caption, or upload a screenshot in the Scam Detector."
        )
        return
    fc.title = title
    # og:description looks like: '12K likes, 300 comments - username on 3 March 2026: "caption..."'
    m = re.match(r'^(?P<stats>.*?)\s+-\s+(?P<user>[\w.]+)\s+on\s+(?P<date>[^:]+):\s*"?(?P<cap>.*?)"?\.?$', desc, re.S)
    if m:
        fc.author, fc.published, fc.caption = "@" + m["user"], m["date"].strip(), m["cap"].strip()
        fc.extra["Engagement"] = m["stats"].strip()
    else:
        fc.caption = desc
    if fc.caption:
        fc.parts.append("caption")
    if fc.kind == "video":
        fc.limitations.append("The reel's audio could not be downloaded without logging in; the caption was checked.")


def _read_x(fc: FetchedContent, language: str) -> None:
    fc.kind = "post"
    m = re.search(r"/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)", urlparse(fc.url).path)
    if not m:
        _read_generic(fc, language)
        fc.kind = "page"
        return
    canonical = f"https://twitter.com/{m.group(1)}/status/{m.group(2)}"
    _, body, _, _ = safe_get(
        f"https://publish.twitter.com/oembed?omit_script=true&dnt=true&url={quote(canonical, safe='')}",
        headers={"Accept": "application/json"},
    )
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise FetchError("X did not return this post. It may be deleted or from a private account.") from exc
    p = parse_page(data.get("html", ""), canonical)
    # oEmbed html: <blockquote class="twitter-tweet"><p>the post</p>&mdash; Name (@handle) <a>date</a></blockquote>
    paras = re.findall(r"<p[^>]*>(.*?)</p>", data.get("html", ""), re.S)
    tweet = _squash(html_lib.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", " ".join(paras)))))
    fc.author = f"{data.get('author_name', '')} (@{m.group(1)})".strip()
    fc.caption = tweet
    fc.title = f"Post by @{m.group(1)}"
    fc.outbound_links = [link for link in p.links if "twitter.com" not in link and "x.com" not in link][:10]
    if tweet:
        fc.parts.append("post text")
    info = _ydl_info(canonical)  # only finds something if the post has a video
    if info and info.get("duration"):
        fc.kind, fc.duration = "video", int(info["duration"])
        _maybe_transcribe(fc, language)


TG_CLASSES = (
    "tgme_widget_message_text",
    "tgme_widget_message_owner_name",
    "tgme_channel_info_header_title",
    "tgme_channel_info_description",
    "tgme_channel_info_counter",
    "tgme_page_title",
    "tgme_page_description",
    "tgme_page_extra",
)


def _read_telegram(fc: FetchedContent, language: str) -> None:
    parts = [p for p in urlparse(fc.url).path.split("/") if p]
    if not parts:
        raise FetchError("Paste the link of a Telegram post or channel.")
    if parts[0].startswith("+") or parts[0] == "joinchat":
        fc.kind = "group"
        fc.extra["Invite"] = "Private Telegram group invite"
        _, body, _, _ = safe_get(fc.url)
        p = parse_page(body, fc.url, TG_CLASSES)
        fc.title = " ".join(p.by_class["tgme_page_title"]) or _meta_title(p)
        fc.caption = " ".join(p.by_class["tgme_page_description"]) or _meta_description(p)
        members = " ".join(p.by_class["tgme_page_extra"])
        if members:
            fc.extra["Members"] = members
        fc.parts.append("group invite page")
        return
    if parts[0] == "s":
        parts = parts[1:]
    channel = parts[0]
    post = parts[1] if len(parts) > 1 and parts[1].isdigit() else None
    if post:
        fc.kind = "post"
        _, body, _, _ = safe_get(f"https://t.me/{channel}/{post}?embed=1&mode=tme")
        p = parse_page(body, fc.url, TG_CLASSES)
        fc.caption = "\n".join(p.by_class["tgme_widget_message_text"])
        fc.author = (p.by_class["tgme_widget_message_owner_name"] or [f"@{channel}"])[0]
        fc.title = f"Telegram post in {fc.author}"
        fc.outbound_links = [link for link in p.links if "t.me" not in link and "telegram" not in link][:10]
        if fc.caption:
            fc.parts.append("post text")
        else:
            fc.limitations.append("This Telegram post has no text, or the channel is private.")
        return
    fc.kind = "channel"
    _, body, _, _ = safe_get(f"https://t.me/s/{channel}")
    p = parse_page(body, fc.url, TG_CLASSES)
    fc.title = (p.by_class["tgme_channel_info_header_title"] or [_meta_title(p)])[0]
    fc.author = f"@{channel}"
    desc = " ".join(p.by_class["tgme_channel_info_description"]) or _meta_description(p)
    fc.caption = desc
    counters = p.by_class["tgme_channel_info_counter"]
    if counters:
        fc.extra["Channel size"] = ", ".join(counters[:3])
    posts = p.by_class["tgme_widget_message_text"][-8:]
    if posts:
        fc.page_text = "\n---\n".join(posts)[:6000]
        fc.parts.append(f"{len(posts)} recent posts")
    if desc:
        fc.parts.append("channel description")
    fc.outbound_links = [link for link in p.links if "t.me" not in link and "telegram" not in link][:10]
    if not (desc or posts):
        fc.limitations.append("This Telegram channel is private or empty, so nothing could be read.")


def _read_whatsapp(fc: FetchedContent, language: str) -> None:
    host = (urlparse(fc.url).hostname or "").lower()
    if host == "wa.me" or host.endswith("api.whatsapp.com"):
        fc.kind = "chat"
        number = re.sub(r"\D", "", urlparse(fc.url).path)
        text = parse_qs(urlparse(fc.url).query).get("text", [""])[0]
        fc.title = "WhatsApp chat link"
        if number:
            fc.extra["Opens a chat with"] = "+" + number
        if text:
            fc.caption = text
            fc.parts.append("pre-filled message")
        return
    fc.kind = "group"
    fc.extra["Invite"] = "WhatsApp group invite"
    try:
        _read_generic(fc, language)
    except FetchError as exc:
        fc.limitations.append(str(exc))
    fc.page_text = ""
