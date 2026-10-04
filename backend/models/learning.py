from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, CreatedAt, UUIDPrimaryKey, utcnow


class Course(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "courses"

    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="beginner")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="course", order_by="Lesson.position", cascade="all, delete-orphan"
    )
    flashcards: Mapped[list[Flashcard]] = relationship(cascade="all, delete-orphan")
    questions: Mapped[list[AssessmentQuestion]] = relationship(cascade="all, delete-orphan")


class Lesson(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "lessons"

    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    est_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    course: Mapped[Course] = relationship(back_populates="lessons")


class Flashcard(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "flashcards"

    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)


class AssessmentQuestion(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "assessment_questions"

    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")


class LearningProgress(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "learning_progress"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_learning_progress_user_course"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    completion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0..100
    completed_lessons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..100
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class QuizAttempt(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "quiz_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)


class LessonTranslation(UUIDPrimaryKey, CreatedAt, Base):
    """Machine translation of a lesson, generated once on first request and reused."""

    __tablename__ = "lesson_translations"
    __table_args__ = (UniqueConstraint("lesson_id", "language", name="uq_lesson_translations_lesson_language"),)

    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
