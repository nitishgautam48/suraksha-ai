"""User feedback on analyses -> labelled data for re-calibrating the risk engine."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import AnalysisFeedback, ScamAnalysis
from backend.services.gamification_service import award
from backend.utils.redact import redact


def disagrees(verdict: str, risk_score: int) -> bool:
    flagged = risk_score >= settings.RISK_MEDIUM_THRESHOLD
    return (verdict == "scam") != flagged


def submit(
    db: Session, user_id: uuid.UUID, analysis_id: uuid.UUID, verdict: str, comment: str | None, share_text: bool
) -> AnalysisFeedback:
    analysis = db.get(ScamAnalysis, analysis_id)
    if analysis is None or analysis.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    fb = db.scalar(
        select(AnalysisFeedback).where(AnalysisFeedback.analysis_id == analysis_id, AnalysisFeedback.user_id == user_id)
    )
    if fb is None:
        fb = AnalysisFeedback(analysis_id=analysis_id, user_id=user_id)
        db.add(fb)
    fb.verdict, fb.comment, fb.share_text = verdict, redact(comment)[0] if comment else None, share_text
    db.flush()
    award(db, user_id, "feedback", ref=str(analysis_id))
    db.commit()
    db.refresh(fb)
    return fb


def admin_list(db: Session, disagreements_only: bool, limit: int, offset: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(AnalysisFeedback, ScamAnalysis)
        .join(ScamAnalysis, ScamAnalysis.id == AnalysisFeedback.analysis_id)
        .order_by(AnalysisFeedback.created_at.desc())
    ).all()
    out = []
    for fb, an in rows:
        d = disagrees(fb.verdict, an.risk_score)
        if disagreements_only and not d:
            continue
        out.append(
            {
                "id": fb.id,
                "analysis_id": fb.analysis_id,
                "verdict": fb.verdict,
                "comment": fb.comment,
                "share_text": fb.share_text,
                "created_at": fb.created_at,
                "risk_score": an.risk_score,
                "risk_level": an.risk_level,
                "source_type": an.source_type,
                "disagrees": d,
            }
        )
    return out[offset : offset + limit]


def export_jsonl(db: Session) -> Iterator[str]:
    """Consented examples in the same format as backend/ai/eval/dataset.jsonl."""
    rows = db.execute(
        select(AnalysisFeedback, ScamAnalysis)
        .join(ScamAnalysis, ScamAnalysis.id == AnalysisFeedback.analysis_id)
        .where(AnalysisFeedback.share_text.is_(True), ScamAnalysis.input_excerpt.is_not(None))
        .order_by(AnalysisFeedback.created_at)
    ).all()
    for fb, an in rows:
        yield (
            json.dumps(
                {
                    "id": str(fb.id),
                    "text": an.input_excerpt,
                    "label": "scam" if fb.verdict == "scam" else "legit",
                    "category": (an.categories or [None])[0] if fb.verdict == "scam" else None,
                    "language": "unknown",
                    "split": "feedback",
                    "source_type": an.source_type,
                    "predicted_score": an.risk_score,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
