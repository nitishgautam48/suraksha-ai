"""Module 6: Learning Center."""

import uuid

from fastapi import APIRouter, Query, Request

from backend.api.deps import DB, CurrentUser, require_permission
from backend.config import settings
from backend.schemas.common import LanguageCode, Message
from backend.schemas.learning import (
    AnswerCheck,
    AssessmentOut,
    AssessmentResult,
    AssessmentSubmit,
    CourseDetail,
    CourseOut,
    FlashcardOut,
    GenerateRequest,
    GenerateResponse,
    LessonCompleteOut,
    LessonOut,
    QuestionResult,
    Topic,
)
from backend.security.rate_limit import limiter
from backend.services import learning_service

router = APIRouter(prefix="/learning", tags=["Learning Center"])


@router.get("/courses", response_model=list[CourseOut])
def courses(user: CurrentUser, db: DB, topic: Topic | None = Query(None)):
    return learning_service.list_courses(db, user.id, topic)


@router.get("/courses/{course_id}", response_model=CourseDetail)
def course(course_id: uuid.UUID, user: CurrentUser, db: DB):
    return learning_service.course_detail(db, user.id, course_id)


@router.get("/lessons/{lesson_id}", response_model=LessonOut)
def lesson(lesson_id: uuid.UUID, user: CurrentUser, db: DB, language: LanguageCode | None = Query(None)):
    """Lesson content in your language (translated once by the local model, then cached)."""
    return learning_service.localized_lesson(db, lesson_id, language or user.language)


@router.post("/lessons/{lesson_id}/complete", response_model=LessonCompleteOut)
def complete_lesson(lesson_id: uuid.UUID, user: CurrentUser, db: DB):
    p = learning_service.complete_lesson(db, user.id, lesson_id)
    return {
        "detail": f"Lesson completed. Course completion: {p.completion}%",
        "completion": p.completion,
        "xp_awarded": getattr(p, "xp_awarded", 0),
    }


@router.post("/questions/{question_id}/check", response_model=QuestionResult)
def check_question(question_id: uuid.UUID, data: AnswerCheck, user: CurrentUser, db: DB):
    """Practice mode: check one answer ("Correct! +20 XP"). XP is given once per question."""
    return learning_service.check_question(db, user.id, question_id, data.answer)


@router.get("/courses/{course_id}/flashcards", response_model=list[FlashcardOut])
def flashcards(course_id: uuid.UUID, user: CurrentUser, db: DB):
    return learning_service.flashcards(db, user.id, course_id)


@router.post("/courses/{course_id}/flashcards/practised", response_model=Message)
def flashcards_practised(course_id: uuid.UUID, user: CurrentUser, db: DB):
    """Record that the user practised this course's flash cards today (learning streak, +XP once a day)."""
    xp = learning_service.flashcards_practised(db, user.id, course_id)
    return {"detail": f"Practice recorded (+{xp} XP)" if xp else "Practice recorded"}


@router.get("/courses/{course_id}/assessment", response_model=AssessmentOut)
def assessment(course_id: uuid.UUID, user: CurrentUser, db: DB):
    """Questions without answers. Submit to /assessment/submit for grading."""
    return {"course_id": course_id, "questions": learning_service.assessment(db, course_id)}


@router.post("/courses/{course_id}/assessment/submit", response_model=AssessmentResult)
def submit(course_id: uuid.UUID, data: AssessmentSubmit, user: CurrentUser, db: DB):
    return learning_service.submit_assessment(db, user.id, course_id, data.answers)


@router.post("/generate", response_model=GenerateResponse)
@limiter.limit(settings.RATE_LIMIT_AI)
def generate(request: Request, data: GenerateRequest, db: DB, user: CurrentUser):
    """Generate a lesson, flash cards, an assessment or a simplification with gemma2:9b, grounded in the
    RAG knowledge base. Saving into a course requires the `educator` role."""
    if data.save_to_course:
        require_permission("content:write")(user)
    return learning_service.generate(db, data.topic, data.kind, data.language, data.count, data.text, data.save_to_course)
