"""Module 1: Scam Detection Engine (image / screenshot / PDF / text)."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse

from backend.api.deps import DB, ConsentedUser, user_language
from backend.config import settings
from backend.schemas.analysis import QuickScanRequest, ScanQueued, ScanResponse, TextScanRequest
from backend.schemas.common import LanguageCode
from backend.security.file_validation import read_and_validate
from backend.security.rate_limit import limiter
from backend.services import scan_service
from backend.services.file_service import save_upload
from backend.utils.cache import cache_set, task_owner_key

router = APIRouter(prefix="/scan", tags=["Scam Detection"])

RESPONSES = {202: {"model": ScanQueued, "description": "Queued for background processing (async=true)"}}


async def _scan_upload(request: Request, file: UploadFile, kind: str, language: str | None, run_async: bool, user, db):
    vf = await read_and_validate(file, kind)
    record = save_upload(db, user.id, vf)
    db.commit()
    lang = user_language(user, language)
    if run_async:
        from backend.workers.tasks import process_scan_file

        task = process_scan_file.delay(str(record.id), lang)
        cache_set(task_owner_key(task.id), str(user.id), ttl=24 * 3600)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=ScanQueued(task_id=task.id, file_id=record.id).model_dump(mode="json"),
        )
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(scan_service.process_file, db, record, lang)


@router.post("/image", response_model=ScanResponse, responses=RESPONSES)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def scan_image(
    request: Request,
    user: ConsentedUser,
    db: DB,
    file: Annotated[UploadFile, File(description="Screenshot / photo (PNG, JPEG, WEBP, BMP, TIFF)")],
    language: Annotated[LanguageCode | None, Form()] = None,
    async_mode: Annotated[bool, Form(alias="async")] = False,
):
    """OCR an image (e.g. WhatsApp screenshot) and analyse it for scam signals."""
    return await _scan_upload(request, file, "image", language, async_mode, user, db)


@router.post("/pdf", response_model=ScanResponse, responses=RESPONSES)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def scan_pdf(
    request: Request,
    user: ConsentedUser,
    db: DB,
    file: Annotated[UploadFile, File(description="PDF brochure, statement or chat export")],
    language: Annotated[LanguageCode | None, Form()] = None,
    async_mode: Annotated[bool, Form(alias="async")] = False,
):
    """Extract text from a PDF (embedded text, or OCR for scanned pages) and analyse it."""
    return await _scan_upload(request, file, "pdf", language, async_mode, user, db)


@router.post("/text", response_model=ScanResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
def scan_text(request: Request, data: TextScanRequest, user: ConsentedUser, db: DB):
    """Analyse any pasted text (SMS, email, chat message) with the full scam engine."""
    lang = user_language(user, data.language)
    analysis, result = scan_service.analyze_text(db, user.id, data.text, lang, "text")
    return scan_service.scan_response(analysis, result, language=lang) | {
        "simple_verdict": scan_service.simple_verdict(db, user.id, analysis.risk_level, lang)
    }


@router.post("/quick")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
def scan_quick(request: Request, data: QuickScanRequest, user: ConsentedUser):
    """Instant rules-only preview (well under a second), shown while the full AI analysis runs.
    Nothing is stored. Call the matching full endpoint for the saved, AI-reviewed result."""
    return scan_service.quick_preview(data.text, data.kind, data.platform, user_language(user, data.language))
