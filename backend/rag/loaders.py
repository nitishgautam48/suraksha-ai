"""Turn knowledge files (Markdown, text, PDF, HTML) into markdown-ish text for chunking."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from backend.rag.chunker import parse_front_matter
from backend.utils.logging import get_logger

log = get_logger(__name__)

SUPPORTED = {".md": "md", ".markdown": "md", ".txt": "txt", ".pdf": "pdf", ".html": "html", ".htm": "html"}


@dataclass
class LoadedDocument:
    body: str
    file_type: str
    meta: dict[str, str] = field(default_factory=dict)
    pages: int | None = None


class _HTMLText(HTMLParser):
    """Extract readable text; drop scripts, styles and page chrome; keep headings as markdown."""

    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "form", "svg", "iframe"}
    BLOCK = {"p", "div", "li", "tr", "br", "section", "article", "table", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif re.fullmatch(r"h[1-4]", tag):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in self.BLOCK:
            self.out.append("\n\n" if tag != "li" else "\n- ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif re.fullmatch(r"h[1-4]", tag):
            self.out.append("\n\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip_depth:
            self.out.append(data)


def html_to_text(raw: str) -> tuple[str, str]:
    parser = _HTMLText()
    parser.feed(raw)
    text = "".join(parser.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text)
    return text.strip(), parser.title.strip()


def pdf_to_text(data: bytes) -> tuple[str, int, str]:
    """Return (text with '## Page N' headings, page_count, pdf_title). Scanned pages are OCR'd if possible."""
    import pymupdf

    parts: list[str] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        title = (doc.metadata or {}).get("title") or ""
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if len(text) < 40:
                try:
                    from PIL import Image

                    from backend.ocr.tesseract import ocr_image_obj

                    pix = page.get_pixmap(dpi=200)
                    text = ocr_image_obj(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).strip()
                except Exception as exc:  # OCR unavailable - keep whatever text exists
                    log.debug("OCR skipped for page %d: %s", i, exc)
            if text:
                parts.append(f"## Page {i}\n\n{text}")
        return "\n\n".join(parts), doc.page_count, title


def _sidecar_meta(path: Path) -> dict[str, str]:
    side = path.with_name(path.name + ".meta.json")
    if side.exists():
        try:
            return {k: str(v) for k, v in json.loads(side.read_text(encoding="utf-8")).items()}
        except (ValueError, OSError) as exc:
            log.warning("Ignoring invalid sidecar %s: %s", side, exc)
    return {}


def load_bytes(data: bytes, file_type: str) -> LoadedDocument:
    if file_type == "pdf":
        body, pages, title = pdf_to_text(data)
        return LoadedDocument(body, "pdf", {"title": title} if title else {}, pages)
    text = data.decode("utf-8", errors="replace")
    if file_type == "html":
        body, title = html_to_text(text)
        return LoadedDocument(body, "html", {"title": title} if title else {})
    if file_type == "md":
        meta, body = parse_front_matter(text)
        return LoadedDocument(body, "md", meta)
    return LoadedDocument(text.strip(), "txt")


def load_file(path: Path) -> LoadedDocument:
    file_type = SUPPORTED.get(path.suffix.lower())
    if file_type is None:
        raise ValueError(f"Unsupported knowledge file type: {path.suffix}")
    doc = load_bytes(path.read_bytes(), file_type)
    doc.meta = {**doc.meta, **_sidecar_meta(path)}
    return doc
