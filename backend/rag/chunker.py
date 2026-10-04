"""Markdown-aware chunking with overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    text: str
    section: str
    index: int


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            for line in raw[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
            raw = raw[end + 4 :]
    return meta, raw.strip()


def _sections(body: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(body))
    if not matches:
        return [("", body)]
    out = []
    if matches[0].start() > 0:
        out.append(("", body[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((m.group(2).strip(), body[m.end() : end]))
    return out


def chunk_markdown(body: str, size: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section, text in _sections(body):
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        buf = ""
        for para in paragraphs:
            if len(buf) + len(para) + 2 <= size:
                buf = f"{buf}\n\n{para}" if buf else para
                continue
            if buf:
                chunks.append(Chunk(buf, section, len(chunks)))
                buf = buf[-overlap:] if overlap else ""
            while len(para) > size:  # very long paragraph: hard split on sentence boundaries
                cut = para.rfind(". ", 0, size)
                cut = cut + 1 if cut > size // 2 else size
                chunks.append(Chunk((buf + " " + para[:cut]).strip(), section, len(chunks)))
                buf, para = para[max(cut - overlap, 0) : cut], para[cut:].strip()
            buf = f"{buf}\n\n{para}".strip() if buf else para
        if buf.strip():
            chunks.append(Chunk(buf.strip(), section, len(chunks)))
    for c in chunks:
        if c.section and not c.text.startswith(c.section):
            c.text = f"{c.section}\n{c.text}"
    return chunks
