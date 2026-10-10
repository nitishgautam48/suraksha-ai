"""Module 2 (WhatsApp message analyzer) and Module 3 (social media analyzer)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select

from backend.api.deps import DB, ConsentedUser, user_language
from backend.config import settings
from backend.models import ScamAnalysis
from backend.schemas.analysis import (
    AnalysisDetail,
    AnalysisSummary,
    FeedbackOut,
    FeedbackRequest,
    LinkAnalyzeRequest,
    LinkAnalyzeResponse,
    MessageAnalyzeRequest,
    MessageAnalyzeResponse,
    SocialAnalyzeRequest,
    SocialAnalyzeResponse,
)
from backend.schemas.common import LanguageCode
from backend.security.file_validation import read_and_validate
from backend.security.rate_limit import limiter
from backend.services import feedback_service, scan_service

router = APIRouter(prefix="/analyze", tags=["Message & Social Analysis"])


@router.post("/message", response_model=MessageAnalyzeResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
def analyze_message(request: Request, data: MessageAnalyzeRequest, user: ConsentedUser, db: DB):
    """Analyse a WhatsApp / SMS message for guaranteed returns, FOMO, fear tactics, fake authority
    and unrealistic profits."""
    lang = user_language(user, data.language)
    analysis, result = scan_service.analyze_text(db, user.id, data.message_text, lang, source="message")
    return scan_service.message_response(analysis, result, lang) | {
        "simple_verdict": scan_service.simple_verdict(db, user.id, analysis.risk_level, lang)
    }


@router.post("/message-image", response_model=MessageAnalyzeResponse)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def analyze_message_image(
    request: Request,
    user: ConsentedUser,
    db: DB,
    file: Annotated[UploadFile, File(description="Screenshot of the WhatsApp / SMS chat")],
    language: Annotated[LanguageCode | None, Form()] = None,
):
    """No copy-paste needed: upload a screenshot of the chat. The text is read (OCR) in memory, the
    image is never stored, and the message is analysed like a pasted one."""
    from starlette.concurrency import run_in_threadpool

    vf = await read_and_validate(file, "image")
    return await run_in_threadpool(scan_service.analyze_message_image, db, user.id, vf.data, user_language(user, language))


@router.post("/social", response_model=SocialAnalyzeResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
def analyze_social(request: Request, data: SocialAnalyzeRequest, user: ConsentedUser, db: DB):
    """Analyse an Instagram caption, Telegram message or YouTube transcript and return the
    risky sections highlighted (character offsets + ready-to-render segments)."""
    return scan_service.analyze_social_post(db, user.id, data.text, data.platform, user_language(user, data.language))


@router.post("/link", response_model=LinkAnalyzeResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
def analyze_link(request: Request, data: LinkAnalyzeRequest, user: ConsentedUser, db: DB):
    """Paste a link to an Instagram reel, YouTube video, Telegram channel/post, X post or any web page.
    Suraksha opens it, reads the caption, spoken words and page text, checks its claims (impossible
    returns, SEBI registration, private-group funnels, payment requests) and returns a detailed,
    reasoned verdict. Never logs in to any platform."""
    return scan_service.analyze_link_url(db, user.id, data.url, user_language(user, data.language))


@router.get("/history", response_model=list[AnalysisSummary])
def history(
    user: ConsentedUser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    risk_level: str | None = Query(None, pattern="^(low|medium|high|critical)$"),
):
    q = select(ScamAnalysis).where(ScamAnalysis.user_id == user.id)
    if risk_level:
        q = q.where(ScamAnalysis.risk_level == risk_level)
    return db.scalars(q.order_by(ScamAnalysis.created_at.desc()).limit(limit).offset(offset)).all()


@router.get("/history/{analysis_id}", response_model=AnalysisDetail)
def history_item(analysis_id: uuid.UUID, user: ConsentedUser, db: DB):
    row = db.get(ScamAnalysis, analysis_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    return row


@router.post("/history/{analysis_id}/feedback", response_model=FeedbackOut)
def feedback(analysis_id: uuid.UUID, data: FeedbackRequest, user: ConsentedUser, db: DB):
    """Tell us whether this analysis was right. Disagreements are reviewed and, with `share_text=true`,
    the message excerpt joins the evaluation dataset used to re-calibrate detection."""
    return feedback_service.submit(db, user.id, analysis_id, data.verdict, data.comment, data.share_text)


@router.get("/history/{analysis_id}/report", tags=["Report a scam"])
def report(analysis_id: uuid.UUID, user: ConsentedUser, db: DB, language: str | None = None):
    """Complaint summary (English, for cybercrime.gov.in / police) + the official reporting steps
    in the user's language: 1930, cybercrime.gov.in, Sanchar Saathi (Chakshu), bank, SEBI SCORES."""
    from backend.services import report_service

    return report_service.build_report(db, user.id, analysis_id, user_language(user, language))


@router.post("/history/{analysis_id}/reported", tags=["Report a scam"])
def reported(analysis_id: uuid.UUID, user: ConsentedUser, db: DB):
    """Mark that the user started reporting this scam (counts towards impact metrics)."""
    from backend.services import report_service

    return {"reported_at": report_service.mark_reported(db, user.id, analysis_id)}
