"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-01 09:17:16.756563+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=300), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)
    op.create_table(
        "courses",
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("slug", name=op.f("uq_courses_slug")),
    )
    op.create_index(op.f("ix_courses_created_at"), "courses", ["created_at"], unique=False)
    op.create_index(op.f("ix_courses_topic"), "courses", ["topic"], unique=False)
    op.create_table(
        "users",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("google_sub", sa.String(length=64), nullable=True),
        sa.Column("auth_provider", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("google_sub", name=op.f("uq_users_google_sub")),
    )
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_table(
        "assessment_questions",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_assessment_questions_course_id_courses"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_questions")),
    )
    op.create_index(op.f("ix_assessment_questions_course_id"), "assessment_questions", ["course_id"], unique=False)
    op.create_index(op.f("ix_assessment_questions_created_at"), "assessment_questions", ["created_at"], unique=False)
    op.create_table(
        "chat_history",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_chat_history_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_history")),
    )
    op.create_index(op.f("ix_chat_history_created_at"), "chat_history", ["created_at"], unique=False)
    op.create_index(op.f("ix_chat_history_user_id"), "chat_history", ["user_id"], unique=False)
    op.create_table(
        "flashcards",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], name=op.f("fk_flashcards_course_id_courses"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flashcards")),
    )
    op.create_index(op.f("ix_flashcards_course_id"), "flashcards", ["course_id"], unique=False)
    op.create_index(op.f("ix_flashcards_created_at"), "flashcards", ["created_at"], unique=False)
    op.create_table(
        "habit_checklist",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=60), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_habit_checklist_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_habit_checklist")),
        sa.UniqueConstraint("user_id", "item_key", name="uq_habit_checklist_user_item"),
    )
    op.create_index(op.f("ix_habit_checklist_created_at"), "habit_checklist", ["created_at"], unique=False)
    op.create_index(op.f("ix_habit_checklist_user_id"), "habit_checklist", ["user_id"], unique=False)
    op.create_table(
        "learning_progress",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("completion", sa.Float(), nullable=False),
        sa.Column("completed_lessons", sa.JSON(), nullable=False),
        sa.Column("best_score", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_learning_progress_course_id_courses"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_learning_progress_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_progress")),
        sa.UniqueConstraint("user_id", "course_id", name="uq_learning_progress_user_course"),
    )
    op.create_index(op.f("ix_learning_progress_course_id"), "learning_progress", ["course_id"], unique=False)
    op.create_index(op.f("ix_learning_progress_created_at"), "learning_progress", ["created_at"], unique=False)
    op.create_index(op.f("ix_learning_progress_user_id"), "learning_progress", ["user_id"], unique=False)
    op.create_table(
        "lessons",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("est_minutes", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], name=op.f("fk_lessons_course_id_courses"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    op.create_index(op.f("ix_lessons_course_id"), "lessons", ["course_id"], unique=False)
    op.create_index(op.f("ix_lessons_created_at"), "lessons", ["created_at"], unique=False)
    op.create_table(
        "quiz_attempts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_quiz_attempts_course_id_courses"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_quiz_attempts_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_attempts")),
    )
    op.create_index(op.f("ix_quiz_attempts_course_id"), "quiz_attempts", ["course_id"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_created_at"), "quiz_attempts", ["created_at"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_user_id"), "quiz_attempts", ["user_id"], unique=False)
    op.create_table(
        "savings_checkins",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_savings_checkins_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_savings_checkins")),
        sa.UniqueConstraint("user_id", "week_start", name="uq_savings_checkins_user_week"),
    )
    op.create_index(op.f("ix_savings_checkins_created_at"), "savings_checkins", ["created_at"], unique=False)
    op.create_index(op.f("ix_savings_checkins_user_id"), "savings_checkins", ["user_id"], unique=False)
    op.create_table(
        "uploaded_files",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_uploaded_files_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploaded_files")),
    )
    op.create_index(op.f("ix_uploaded_files_created_at"), "uploaded_files", ["created_at"], unique=False)
    op.create_index(op.f("ix_uploaded_files_sha256"), "uploaded_files", ["sha256"], unique=False)
    op.create_index(op.f("ix_uploaded_files_user_id"), "uploaded_files", ["user_id"], unique=False)
    op.create_table(
        "user_activity",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_activity_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_activity")),
        sa.UniqueConstraint("user_id", "activity_date", "kind", name="uq_user_activity_day_kind"),
    )
    op.create_index(op.f("ix_user_activity_activity_date"), "user_activity", ["activity_date"], unique=False)
    op.create_index(op.f("ix_user_activity_created_at"), "user_activity", ["created_at"], unique=False)
    op.create_index(op.f("ix_user_activity_user_id"), "user_activity", ["user_id"], unique=False)
    op.create_table(
        "scam_analyses",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("safe_practices", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("input_excerpt", sa.Text(), nullable=True),
        sa.Column("file_id", sa.Uuid(), nullable=True),
        sa.Column("llm_used", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"], ["uploaded_files.id"], name=op.f("fk_scam_analyses_file_id_uploaded_files"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_scam_analyses_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scam_analyses")),
    )
    op.create_index(op.f("ix_scam_analyses_created_at"), "scam_analyses", ["created_at"], unique=False)
    op.create_index(op.f("ix_scam_analyses_risk_level"), "scam_analyses", ["risk_level"], unique=False)
    op.create_index(op.f("ix_scam_analyses_user_id"), "scam_analyses", ["user_id"], unique=False)
    op.create_table(
        "safety_alerts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_type", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["scam_analyses.id"], name=op.f("fk_safety_alerts_analysis_id_scam_analyses"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_safety_alerts_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_safety_alerts")),
    )
    op.create_index(op.f("ix_safety_alerts_alert_type"), "safety_alerts", ["alert_type"], unique=False)
    op.create_index(op.f("ix_safety_alerts_created_at"), "safety_alerts", ["created_at"], unique=False)
    op.create_index(op.f("ix_safety_alerts_user_id"), "safety_alerts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_safety_alerts_user_id"), table_name="safety_alerts")
    op.drop_index(op.f("ix_safety_alerts_created_at"), table_name="safety_alerts")
    op.drop_index(op.f("ix_safety_alerts_alert_type"), table_name="safety_alerts")
    op.drop_table("safety_alerts")
    op.drop_index(op.f("ix_scam_analyses_user_id"), table_name="scam_analyses")
    op.drop_index(op.f("ix_scam_analyses_risk_level"), table_name="scam_analyses")
    op.drop_index(op.f("ix_scam_analyses_created_at"), table_name="scam_analyses")
    op.drop_table("scam_analyses")
    op.drop_index(op.f("ix_user_activity_user_id"), table_name="user_activity")
    op.drop_index(op.f("ix_user_activity_created_at"), table_name="user_activity")
    op.drop_index(op.f("ix_user_activity_activity_date"), table_name="user_activity")
    op.drop_table("user_activity")
    op.drop_index(op.f("ix_uploaded_files_user_id"), table_name="uploaded_files")
    op.drop_index(op.f("ix_uploaded_files_sha256"), table_name="uploaded_files")
    op.drop_index(op.f("ix_uploaded_files_created_at"), table_name="uploaded_files")
    op.drop_table("uploaded_files")
    op.drop_index(op.f("ix_savings_checkins_user_id"), table_name="savings_checkins")
    op.drop_index(op.f("ix_savings_checkins_created_at"), table_name="savings_checkins")
    op.drop_table("savings_checkins")
    op.drop_index(op.f("ix_quiz_attempts_user_id"), table_name="quiz_attempts")
    op.drop_index(op.f("ix_quiz_attempts_created_at"), table_name="quiz_attempts")
    op.drop_index(op.f("ix_quiz_attempts_course_id"), table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index(op.f("ix_lessons_created_at"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_course_id"), table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(op.f("ix_learning_progress_user_id"), table_name="learning_progress")
    op.drop_index(op.f("ix_learning_progress_created_at"), table_name="learning_progress")
    op.drop_index(op.f("ix_learning_progress_course_id"), table_name="learning_progress")
    op.drop_table("learning_progress")
    op.drop_index(op.f("ix_habit_checklist_user_id"), table_name="habit_checklist")
    op.drop_index(op.f("ix_habit_checklist_created_at"), table_name="habit_checklist")
    op.drop_table("habit_checklist")
    op.drop_index(op.f("ix_flashcards_created_at"), table_name="flashcards")
    op.drop_index(op.f("ix_flashcards_course_id"), table_name="flashcards")
    op.drop_table("flashcards")
    op.drop_index(op.f("ix_chat_history_user_id"), table_name="chat_history")
    op.drop_index(op.f("ix_chat_history_created_at"), table_name="chat_history")
    op.drop_table("chat_history")
    op.drop_index(op.f("ix_assessment_questions_created_at"), table_name="assessment_questions")
    op.drop_index(op.f("ix_assessment_questions_course_id"), table_name="assessment_questions")
    op.drop_table("assessment_questions")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_courses_topic"), table_name="courses")
    op.drop_index(op.f("ix_courses_created_at"), table_name="courses")
    op.drop_table("courses")
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")
