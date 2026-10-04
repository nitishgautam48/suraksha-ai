"""Upload validation: size limits, extension allow-list and magic-byte sniffing.

The declared Content-Type is never trusted; we inspect the bytes themselves.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

from backend.config import settings


@dataclass(frozen=True)
class ValidatedFile:
    data: bytes
    kind: str  # image | pdf | audio
    mime: str
    ext: str
    original_name: str | None


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".oga", ".opus", ".webm", ".flac", ".aac", ".mp4"}


def sniff(data: bytes) -> tuple[str, str, str] | None:
    """Return (kind, mime, ext) from magic bytes, or None if unrecognised."""
    head = data[:64]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png", ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg", ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp", ".webp"
    if head.startswith(b"BM"):
        return "image", "image/bmp", ".bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image", "image/tiff", ".tiff"
    if head.startswith(b"%PDF-"):
        return "pdf", "application/pdf", ".pdf"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "audio/wav", ".wav"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio", "audio/mpeg", ".mp3"
    if head.startswith(b"OggS"):
        return "audio", "audio/ogg", ".ogg"
    if head.startswith(b"fLaC"):
        return "audio", "audio/flac", ".flac"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio", "audio/webm", ".webm"
    if head[4:8] == b"ftyp":
        return "audio", "audio/mp4", ".m4a"
    return None


def _too_large(max_mb: int) -> HTTPException:
    return HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {max_mb} MB limit")


async def read_and_validate(upload: UploadFile, expected_kind: str) -> ValidatedFile:
    max_mb = settings.MAX_AUDIO_MB if expected_kind == "audio" else settings.MAX_UPLOAD_MB
    limit = max_mb * 1024 * 1024
    buf = io.BytesIO()
    while chunk := await upload.read(1024 * 1024):
        buf.write(chunk)
        if buf.tell() > limit:
            raise _too_large(max_mb)
    data = buf.getvalue()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    name = (upload.filename or "").lower()
    ext = name[name.rfind(".") :] if "." in name else ""
    allowed = {"image": IMAGE_EXTS, "pdf": PDF_EXTS, "audio": AUDIO_EXTS}[expected_kind]
    if ext and ext not in allowed:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Extension {ext} not allowed")

    sniffed = sniff(data)
    if not sniffed or sniffed[0] != expected_kind:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"File content is not a supported {expected_kind}")
    kind, mime, sniffed_ext = sniffed

    if kind == "image":
        _verify_image(data)
    elif kind == "pdf":
        _verify_pdf(data)

    return ValidatedFile(data=data, kind=kind, mime=mime, ext=sniffed_ext, original_name=upload.filename)


def _verify_image(data: bytes) -> None:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Corrupt or unsafe image") from exc


def _verify_pdf(data: bytes) -> None:
    import pymupdf

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password-protected PDFs are not supported")
            if doc.page_count == 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF has no pages")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Corrupt PDF") from exc


KNOWLEDGE_EXTS = {".pdf": "pdf", ".md": "md", ".markdown": "md", ".txt": "txt", ".html": "html", ".htm": "html"}


async def read_knowledge_upload(upload: UploadFile) -> tuple[bytes, str, str]:
    """Validate an admin knowledge-base upload. Returns (data, file_type, extension)."""
    limit = settings.KNOWLEDGE_MAX_MB * 1024 * 1024
    buf = io.BytesIO()
    while chunk := await upload.read(1024 * 1024):
        buf.write(chunk)
        if buf.tell() > limit:
            raise _too_large(settings.KNOWLEDGE_MAX_MB)
    data = buf.getvalue()
    name = (upload.filename or "").lower()
    ext = name[name.rfind(".") :] if "." in name else ""
    if ext not in KNOWLEDGE_EXTS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .pdf, .md, .txt or .html file")
    if not data.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    file_type = KNOWLEDGE_EXTS[ext]
    if file_type == "pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File content is not a PDF")
        _verify_pdf(data)
    else:
        if b"\x00" in data[:8192]:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Text documents must not be binary")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Text documents must be UTF-8") from exc
    return data, file_type, ".md" if file_type == "md" else f".{file_type}"
