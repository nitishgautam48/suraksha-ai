"""Idempotent database seeding (courses + bootstrap admin)."""

from __future__ import annotations

from sqlalchemy import select

from backend.database.session import session_scope
from backend.models import AssessmentQuestion, Course, Flashcard, Lesson
from backend.seed.content import COURSES
from backend.services.auth_service import bootstrap_admin
from backend.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


def seed_courses() -> int:
    created = 0
    with session_scope() as db:
        for pos, c in enumerate(COURSES):
            if db.scalar(select(Course).where(Course.slug == c["slug"])):
                continue
            course = Course(
                slug=c["slug"],
                title=c["title"],
                topic=c["topic"],
                description=c["description"],
                level=c["level"],
                position=pos,
            )
            course.lessons = [
                Lesson(title=t, est_minutes=m, content=body.strip(), position=i) for i, (t, m, body) in enumerate(c["lessons"])
            ]
            course.flashcards = [Flashcard(front=f, back=b) for f, b in c["flashcards"]]
            course.questions = [
                AssessmentQuestion(question=q, options=opts, correct_index=ci, explanation=ex)
                for q, opts, ci, ex in c["questions"]
            ]
            db.add(course)
            created += 1
    return created


def run() -> None:
    configure_logging()
    n = seed_courses()
    log.info("Seeded %d course(s)", n)
    with session_scope() as db:
        bootstrap_admin(db)


if __name__ == "__main__":
    run()
