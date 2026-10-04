"""Import every model so Base.metadata is complete (used by Alembic)."""

from backend.models.activity import (  # noqa: F401
    AuditLog,
    ChatHistory,
    HabitChecklistItem,
    SafetyAlert,
    SavingsCheckin,
    UserActivity,
)
from backend.models.family import EmergencyContact, HelpRequest, ReadinessItem  # noqa: F401
from backend.models.gamification import UserAchievement, XPEvent  # noqa: F401
from backend.models.knowledge import KnowledgeDocument  # noqa: F401
from backend.models.learning import (  # noqa: F401
    AssessmentQuestion,
    Course,
    Flashcard,
    LearningProgress,
    Lesson,
    LessonTranslation,
    QuizAttempt,
)
from backend.models.scan import AnalysisFeedback, ScamAnalysis, UploadedFile  # noqa: F401
from backend.models.user import AuthToken, User  # noqa: F401
