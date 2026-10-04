from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.common import LanguageCode, ORMModel

Topic = Literal["scam_detection", "upi_frauds", "cyber_safety", "financial_literacy"]


class LessonOut(ORMModel):
    id: uuid.UUID
    title: str
    content: str
    position: int
    est_minutes: int
    language: str = "en"
    translated: bool = False


class LessonBrief(ORMModel):
    id: uuid.UUID
    title: str
    position: int
    est_minutes: int


class CourseOut(ORMModel):
    id: uuid.UUID
    slug: str
    title: str
    topic: str
    description: str
    level: str
    lesson_count: int = 0
    completion: float = 0.0


class CourseDetail(CourseOut):
    lessons: list[LessonBrief]
    completed_lessons: list[str] = []
    best_score: float | None = None


class FlashcardOut(ORMModel):
    id: uuid.UUID
    front: str
    back: str


class QuestionOut(ORMModel):
    id: uuid.UUID
    question: str
    options: list[str]


class AssessmentOut(BaseModel):
    course_id: uuid.UUID
    questions: list[QuestionOut]


class AssessmentSubmit(BaseModel):
    answers: dict[uuid.UUID, int] = Field(description="question_id -> selected option index")


class QuestionResult(BaseModel):
    question_id: uuid.UUID
    correct: bool
    correct_index: int
    explanation: str
    xp_awarded: int = 0


class AnswerCheck(BaseModel):
    answer: int = Field(ge=0, le=3)


class LessonCompleteOut(BaseModel):
    detail: str
    completion: float
    xp_awarded: int


class AssessmentResult(BaseModel):
    xp_awarded: int = 0
    score: int
    total: int
    percent: float
    passed: bool
    results: list[QuestionResult]
    completion: float


class ProgressItem(BaseModel):
    course_id: uuid.UUID
    course_title: str
    topic: str
    completion: float
    lessons_completed: int
    lesson_count: int
    best_score: float | None
    updated_at: datetime | None


class ProgressOut(BaseModel):
    overall_completion: float
    learning_streak_days: int
    longest_streak_days: int
    quizzes_taken: int
    average_quiz_score: float | None
    courses: list[ProgressItem]


class GenerateRequest(BaseModel):
    topic: Topic
    kind: Literal["lesson", "flashcards", "assessment", "simplify"] = "lesson"
    language: LanguageCode = "en"
    count: int = Field(default=5, ge=1, le=10)
    text: str | None = Field(default=None, max_length=4000, description="Text to simplify (kind=simplify)")
    save_to_course: bool = False


class GenerateResponse(BaseModel):
    topic: str
    kind: str
    language: str
    model: str | None
    content: dict
    grounded_sources: list[dict]
    saved: bool = False
