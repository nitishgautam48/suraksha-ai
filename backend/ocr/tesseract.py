"""Tesseract OCR for screenshots, chat captures and PDFs (scanned or digital)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageOps

from backend.config import settings
from backend.i18n import LANGUAGES
from backend.utils.logging import get_logger

log = get_logger(__name__)


class OCRUnavailable(Exception):
    pass


@dataclass
class OCRResult:
    text: str
    pages: int
    method: str  # tesseract | pdf_text | mixed
    languages: str


@lru_cache(maxsize=1)
def installed_languages() -> frozenset[str]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        return frozenset(pytesseract.get_languages(config=""))
    except Exception as exc:
        raise OCRUnavailable(f"Tesseract is not installed or not on PATH: {exc}") from exc


def available_languages(language: str | None = None) -> str:
    """Base languages (eng+hin) plus the script of the user's language, limited to installed packs.
    Loading only the needed scripts keeps OCR fast and accurate."""
    installed = installed_languages()
    wanted = settings.OCR_LANGUAGES.split("+")
    if language in LANGUAGES:
        wanted.append(LANGUAGES[language].tesseract)
    chosen = [lang for lang in dict.fromkeys(wanted) if lang in installed]
    return "+".join(chosen or (["eng"] if "eng" in installed else sorted(installed)[:1]))


def _preprocess(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    gray = ImageOps.grayscale(img)
    # Upscale small screenshots - Tesseract works best around 300 DPI equivalent.
    if gray.width < 1200:
        factor = min(3.0, 1200 / max(gray.width, 1))
        gray = gray.resize((int(gray.width * factor), int(gray.height * factor)), Image.LANCZOS)
    # Dark-mode chat screenshots: invert so text is dark on light.
    if sum(gray.resize((32, 32)).getdata()) / 1024 < 110:
        gray = ImageOps.invert(gray)
    return ImageOps.autocontrast(gray)


def ocr_image_obj(img: Image.Image, language: str | None = None) -> str:
    import pytesseract

    langs = available_languages(language)
    try:
        return pytesseract.image_to_string(_preprocess(img), lang=langs, config="--oem 1 --psm 3", timeout=60)
    except RuntimeError as exc:  # timeout
        raise OCRUnavailable(f"OCR timed out: {exc}") from exc


def ocr_image(data: bytes, language: str | None = None) -> OCRResult:
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        text = ocr_image_obj(img, language)
    return OCRResult(text=text.strip(), pages=1, method="tesseract", languages=available_languages(language))


def ocr_pdf(data: bytes, language: str | None = None) -> OCRResult:
    """Use embedded text where present; rasterise and OCR pages that are scanned images."""
    import pymupdf

    texts: list[str] = []
    methods: set[str] = set()
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        n = min(doc.page_count, settings.MAX_PDF_PAGES)
        for i in range(n):
            page = doc.load_page(i)
            embedded = page.get_text("text").strip()
            if len(embedded) >= 40:
                texts.append(embedded)
                methods.add("pdf_text")
                continue
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            texts.append(ocr_image_obj(img, language).strip())
            methods.add("tesseract")
    method = "mixed" if len(methods) > 1 else (methods.pop() if methods else "pdf_text")
    langs = available_languages(language) if method != "pdf_text" else "embedded"
    return OCRResult(text="\n\n".join(t for t in texts if t), pages=n, method=method, languages=langs)
