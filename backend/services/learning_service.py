"""Module 6: Learning Center - courses, lessons, flash cards, assessments, AI generation."""

from __future__ import annotations

import random
import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.ai import prompts
from backend.ai.guardrails import output_violates_policy
from backend.ai.ollama_client import LLMUnavailable, get_ollama, model_for
from backend.config import settings
from backend.models import AssessmentQuestion, Course, Flashcard, LearningProgress, Lesson, LessonTranslation, QuizAttempt
from backend.rag.retriever import format_context, retrieve, sources_payload
from backend.services.activity_service import record_activity, streaks
from backend.services.gamification_service import award, check_achievements
from backend.utils.cache import cache_get, cache_key, cache_set

PASS_PERCENT = 60.0
TOPIC_TITLES = {
    "scam_detection": "Investment scam detection",
    "upi_frauds": "UPI frauds",
    "cyber_safety": "Cyber safety",
    "financial_literacy": "Financial literacy and safe money habits",
}


def _course_or_404(db: Session, course_id: uuid.UUID) -> Course:
    course = db.scalar(
        select(Course).where(Course.id == course_id, Course.is_published.is_(True)).options(selectinload(Course.lessons))
    )
    if not course:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return course


def _progress(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, create: bool = False) -> LearningProgress | None:
    p = db.scalar(select(LearningProgress).where(LearningProgress.user_id == user_id, LearningProgress.course_id == course_id))
    if p is None and create:
        p = LearningProgress(user_id=user_id, course_id=course_id, completion=0.0, completed_lessons=[])
        db.add(p)
        db.flush()
    return p


def _recompute(p: LearningProgress, lesson_count: int) -> None:
    """Completion = 80% lessons + 20% for passing the assessment."""
    lesson_part = (len(p.completed_lessons) / lesson_count * 80.0) if lesson_count else 80.0
    quiz_part = 20.0 if (p.best_score or 0) >= PASS_PERCENT else 0.0
    p.completion = round(min(lesson_part + quiz_part, 100.0), 1)


def list_courses(db: Session, user_id: uuid.UUID, topic: str | None = None) -> list[dict[str, Any]]:
    q = select(Course).where(Course.is_published.is_(True)).options(selectinload(Course.lessons)).order_by(Course.position)
    if topic:
        q = q.where(Course.topic == topic)
    courses = db.scalars(q).all()
    progress = {p.course_id: p for p in db.scalars(select(LearningProgress).where(LearningProgress.user_id == user_id)).all()}
    return [
        {
            "id": c.id,
            "slug": c.slug,
            "title": c.title,
            "topic": c.topic,
            "description": c.description,
            "level": c.level,
            "lesson_count": len(c.lessons),
            "completion": progress[c.id].completion if c.id in progress else 0.0,
        }
        for c in courses
    ]


def course_detail(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> dict[str, Any]:
    c = _course_or_404(db, course_id)
    p = _progress(db, user_id, course_id)
    return {
        "id": c.id,
        "slug": c.slug,
        "title": c.title,
        "topic": c.topic,
        "description": c.description,
        "level": c.level,
        "lesson_count": len(c.lessons),
        "lessons": c.lessons,
        "completion": p.completion if p else 0.0,
        "completed_lessons": p.completed_lessons if p else [],
        "best_score": p.best_score if p else None,
    }


def get_lesson(db: Session, lesson_id: uuid.UUID) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    return lesson


def localized_lesson(db: Session, lesson_id: uuid.UUID, language: str | None) -> dict[str, Any]:
    """Lesson in the requested language. Seeded lessons are English; other languages are translated by
    the secondary model once and stored. Falls back to English (translated=False) if the LLM is unavailable."""
    lesson = get_lesson(db, lesson_id)
    base = {
        "id": lesson.id,
        "title": lesson.title,
        "content": lesson.content,
        "position": lesson.position,
        "est_minutes": lesson.est_minutes,
        "language": "en",
        "translated": False,
    }
    if not language or language == "en":
        return base
    tr = db.scalar(
        select(LessonTranslation).where(LessonTranslation.lesson_id == lesson.id, LessonTranslation.language == language)
    )
    if tr is None:
        model = model_for(language, settings.OLLAMA_SECONDARY_MODEL)
        try:
            data = get_ollama().chat_json(
                [
                    {"role": "system", "content": prompts.EDUCATOR_SYSTEM},
                    {
                        "role": "user",
                        "content": prompts.TRANSLATE_LESSON.format(
                            language=prompts.LANGUAGE_NAMES.get(language, "English"), title=lesson.title, content=lesson.content
                        ),
                    },
                ],
                model=model,
                temperature=0.2,
                max_tokens=2000,
            )
            title, content = str(data.get("title") or "").strip(), str(data.get("content") or "").strip()
        except LLMUnavailable:
            return base
        if not title or not content or output_violates_policy(content):
            return base
        tr = LessonTranslation(lesson_id=lesson.id, language=language, title=title[:300], content=content, model=model)
        db.add(tr)
        db.commit()
    return {**base, "title": tr.title, "content": tr.content, "language": language, "translated": True}


def complete_lesson(db: Session, user_id: uuid.UUID, lesson_id: uuid.UUID) -> LearningProgress:
    lesson = get_lesson(db, lesson_id)
    course = _course_or_404(db, lesson.course_id)
    p = _progress(db, user_id, course.id, create=True)
    if str(lesson.id) not in p.completed_lessons:
        p.completed_lessons = [*p.completed_lessons, str(lesson.id)]  # reassign so JSON change is tracked
    _recompute(p, len(course.lessons))
    record_activity(db, user_id, "lesson")
    p.xp_awarded = award(db, user_id, "lesson_complete", ref=str(lesson.id)) + _daily(db, user_id)
    db.commit()
    return p


def flashcards(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> list[Flashcard]:
    _course_or_404(db, course_id)
    record_activity(db, user_id, "flashcards")
    award(db, user_id, "flashcards", ref=f"{course_id}:{date.today().isoformat()}")
    _daily(db, user_id)
    db.commit()
    return list(db.scalars(select(Flashcard).where(Flashcard.course_id == course_id)).all())


def assessment(db: Session, course_id: uuid.UUID, shuffle: bool = True) -> list[AssessmentQuestion]:
    _course_or_404(db, course_id)
    qs = list(db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.course_id == course_id)).all())
    if shuffle:
        random.shuffle(qs)
    return qs


def submit_assessment(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, answers: dict[uuid.UUID, int]) -> dict[str, Any]:
    course = _course_or_404(db, course_id)
    questions = assessment(db, course_id, shuffle=False)
    if not questions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This course has no assessment")
    results, score, xp = [], 0, 0
    for q in questions:
        chosen = answers.get(q.id)
        correct = chosen == q.correct_index
        score += int(correct)
        gained = award(db, user_id, "quiz_correct", ref=str(q.id), check=False) if correct else 0
        xp += gained
        results.append(
            {
                "question_id": q.id,
                "correct": correct,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "xp_awarded": gained,
            }
        )
    total = len(questions)
    percent = round(score / total * 100, 1)
    db.add(QuizAttempt(user_id=user_id, course_id=course_id, score=score, total=total))
    p = _progress(db, user_id, course_id, create=True)
    p.best_score = max(p.best_score or 0.0, percent)
    _recompute(p, len(course.lessons))
    record_activity(db, user_id, "quiz")
    db.flush()
    if percent >= PASS_PERCENT:
        xp += award(db, user_id, "quiz_pass", ref=str(course_id), check=False)
    xp += _daily(db, user_id)
    check_achievements(db, user_id)
    db.commit()
    return {
        "xp_awarded": xp,
        "score": score,
        "total": total,
        "percent": percent,
        "passed": percent >= PASS_PERCENT,
        "results": results,
        "completion": p.completion,
    }


def check_question(db: Session, user_id: uuid.UUID, question_id: uuid.UUID, answer: int) -> dict[str, Any]:
    """Check one answer (practice mode). XP is granted the first time a question is answered correctly."""
    q = db.get(AssessmentQuestion, question_id)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    _course_or_404(db, q.course_id)
    correct = answer == q.correct_index
    gained = award(db, user_id, "quiz_correct", ref=str(q.id)) if correct else 0
    record_activity(db, user_id, "quiz")
    gained += _daily(db, user_id)
    db.commit()
    return {
        "question_id": q.id,
        "correct": correct,
        "correct_index": q.correct_index,
        "explanation": q.explanation,
        "xp_awarded": gained,
    }


def _daily(db: Session, user_id: uuid.UUID) -> int:
    return award(db, user_id, "daily_learning", ref=date.today().isoformat())


def progress_overview(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    courses = db.scalars(
        select(Course).where(Course.is_published.is_(True)).options(selectinload(Course.lessons)).order_by(Course.position)
    ).all()
    progress = {p.course_id: p for p in db.scalars(select(LearningProgress).where(LearningProgress.user_id == user_id)).all()}
    items = []
    for c in courses:
        p = progress.get(c.id)
        items.append(
            {
                "course_id": c.id,
                "course_title": c.title,
                "topic": c.topic,
                "completion": p.completion if p else 0.0,
                "lessons_completed": len(p.completed_lessons) if p else 0,
                "lesson_count": len(c.lessons),
                "best_score": p.best_score if p else None,
                "updated_at": p.updated_at if p else None,
            }
        )
    overall = round(sum(i["completion"] for i in items) / len(items), 1) if items else 0.0
    quizzes = db.execute(
        select(func.count(QuizAttempt.id), func.avg(QuizAttempt.score * 100.0 / QuizAttempt.total)).where(
            QuizAttempt.user_id == user_id
        )
    ).one()
    current, longest = streaks(db, user_id)
    return {
        "overall_completion": overall,
        "learning_streak_days": current,
        "longest_streak_days": longest,
        "quizzes_taken": quizzes[0] or 0,
        "average_quiz_score": round(float(quizzes[1]), 1) if quizzes[1] is not None else None,
        "courses": items,
    }


# ---- AI content generation (gemma2:9b + RAG grounding) ----------------------------------------
def _validate_generated(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    if kind == "lesson":
        if not isinstance(data.get("content"), str) or not data["content"].strip():
            raise ValueError("lesson content missing")
        return {
            "title": str(data.get("title", "Lesson"))[:200],
            "content": data["content"],
            "est_minutes": int(data.get("est_minutes") or 5),
        }
    if kind == "flashcards":
        cards = [
            {"front": str(c["front"]), "back": str(c["back"])}
            for c in data.get("flashcards", [])
            if isinstance(c, dict) and c.get("front") and c.get("back")
        ]
        if not cards:
            raise ValueError("no flashcards")
        return {"flashcards": cards}
    if kind == "assessment":
        qs = []
        for q in data.get("questions", []):
            opts = q.get("options") if isinstance(q, dict) else None
            ci = q.get("correct_index") if isinstance(q, dict) else None
            if isinstance(opts, list) and len(opts) == 4 and isinstance(ci, int) and 0 <= ci < 4 and q.get("question"):
                qs.append(
                    {
                        "question": str(q["question"]),
                        "options": [str(o) for o in opts],
                        "correct_index": ci,
                        "explanation": str(q.get("explanation", "")),
                    }
                )
        if not qs:
            raise ValueError("no valid questions")
        return {"questions": qs}
    raise ValueError("unknown kind")


def generate(
    db: Session, topic: str, kind: str, language: str, count: int, text: str | None, save_to_course: bool
) -> dict[str, Any]:
    model = settings.OLLAMA_SECONDARY_MODEL
    lang_name = prompts.LANGUAGE_NAMES.get(language, "English")
    topic_title = TOPIC_TITLES[topic]

    if kind == "simplify":
        if not text:
            raise HTTPException(422, "'text' is required for kind=simplify")
        try:
            out = get_ollama().chat(
                [
                    {"role": "system", "content": prompts.EDUCATOR_SYSTEM},
                    {"role": "user", "content": prompts.SIMPLIFY.format(language=lang_name, text=text)},
                ],
                model=model,
                temperature=0.3,
            )
        except LLMUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Content generation unavailable: {exc}") from exc
        if output_violates_policy(out):
            raise HTTPException(422, "Generated text violated the no-advice policy")
        return {
            "topic": topic,
            "kind": kind,
            "language": language,
            "model": model,
            "content": {"text": out.strip()},
            "grounded_sources": [],
            "saved": False,
        }

    chunks = retrieve(topic_title, k=5, min_score=0.2)
    context = format_context(chunks)
    template = {
        "lesson": prompts.GENERATE_LESSON,
        "flashcards": prompts.GENERATE_FLASHCARDS,
        "assessment": prompts.GENERATE_ASSESSMENT,
    }[kind]
    key = cache_key("gen", model, topic, kind, language, str(count))
    content = cache_get(key) if not save_to_course else None
    if content is None:
        try:
            raw = get_ollama().chat_json(
                [
                    {"role": "system", "content": prompts.EDUCATOR_SYSTEM},
                    {
                        "role": "user",
                        "content": template.format(context=context, topic=topic_title, language=lang_name, count=count),
                    },
                ],
                model=model,
                temperature=0.4,
                max_tokens=1800,
            )
            content = _validate_generated(kind, raw)
        except LLMUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Content generation unavailable: {exc}") from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Model returned invalid content: {exc}") from exc
        import json

        if output_violates_policy(json.dumps(content, ensure_ascii=False)):
            raise HTTPException(422, "Generated content violated the no-advice policy")
        cache_set(key, content, ttl=24 * 3600)

    saved = False
    if save_to_course:
        course = db.scalar(select(Course).where(Course.topic == topic).order_by(Course.position))
        if course:
            if kind == "lesson":
                pos = (db.scalar(select(func.max(Lesson.position)).where(Lesson.course_id == course.id)) or 0) + 1
                db.add(
                    Lesson(
                        course_id=course.id,
                        title=content["title"],
                        content=content["content"],
                        est_minutes=content["est_minutes"],
                        position=pos,
                    )
                )
            elif kind == "flashcards":
                db.add_all([Flashcard(course_id=course.id, **c) for c in content["flashcards"]])
            else:
                db.add_all([AssessmentQuestion(course_id=course.id, **q) for q in content["questions"]])
            db.commit()
            saved = True
    return {
        "topic": topic,
        "kind": kind,
        "language": language,
        "model": model,
        "content": content,
        "grounded_sources": sources_payload(chunks),
        "saved": saved,
    }
