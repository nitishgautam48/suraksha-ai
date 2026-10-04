"""phone family elder rewards languages

Revision ID: 0003
Revises: 0002

Adds phone login (users.phone/phone_verified, nullable email), profile (city, user_type),
preferences + elder mode, XP / achievements, emergency contacts + help requests, lesson translations.
Create Date: 2026-10-01 13:29:49.960294+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "emergency_contacts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("relationship", sa.String(length=40), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("notify_on_high_risk", sa.Boolean(), nullable=False),
        sa.Column("notified_added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_emergency_contacts_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_emergency_contacts")),
    )
    op.create_index(op.f("ix_emergency_contacts_created_at"), "emergency_contacts", ["created_at"], unique=False)
    op.create_index(op.f("ix_emergency_contacts_user_id"), "emergency_contacts", ["user_id"], unique=False)
    op.create_table(
        "user_achievements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_achievements_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_achievements")),
        sa.UniqueConstraint("user_id", "key", name="uq_user_achievements_user_key"),
    )
    op.create_index(op.f("ix_user_achievements_created_at"), "user_achievements", ["created_at"], unique=False)
    op.create_index(op.f("ix_user_achievements_user_id"), "user_achievements", ["user_id"], unique=False)
    op.create_table(
        "xp_events",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("ref", sa.String(length=120), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_xp_events_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xp_events")),
        sa.UniqueConstraint("user_id", "action", "ref", name="uq_xp_events_user_action_ref"),
    )
    op.create_index(op.f("ix_xp_events_created_at"), "xp_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_xp_events_user_id"), "xp_events", ["user_id"], unique=False)
    op.create_table(
        "lesson_translations",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_lesson_translations_lesson_id_lessons"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_translations")),
        sa.UniqueConstraint("lesson_id", "language", name="uq_lesson_translations_lesson_language"),
    )
    op.create_index(op.f("ix_lesson_translations_created_at"), "lesson_translations", ["created_at"], unique=False)
    op.create_index(op.f("ix_lesson_translations_lesson_id"), "lesson_translations", ["lesson_id"], unique=False)
    op.create_table(
        "help_requests",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["scam_analyses.id"], name=op.f("fk_help_requests_analysis_id_scam_analyses"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_help_requests_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_help_requests")),
    )
    op.create_index(op.f("ix_help_requests_created_at"), "help_requests", ["created_at"], unique=False)
    op.create_index(op.f("ix_help_requests_user_id"), "help_requests", ["user_id"], unique=False)
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("phone_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("city", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("user_type", sa.String(length=30), nullable=True))
    op.add_column("users", sa.Column("preferences", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("users", sa.Column("xp", sa.Integer(), server_default="0", nullable=False))
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=254), nullable=True)
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)


def downgrade() -> None:
    # Phone-only accounts have no email; they must be removed before email can be NOT NULL again.
    op.execute("DELETE FROM users WHERE email IS NULL")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=254), nullable=False)
    op.drop_column("users", "xp")
    op.drop_column("users", "preferences")
    op.drop_column("users", "user_type")
    op.drop_column("users", "city")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
    op.drop_index(op.f("ix_help_requests_user_id"), table_name="help_requests")
    op.drop_index(op.f("ix_help_requests_created_at"), table_name="help_requests")
    op.drop_table("help_requests")
    op.drop_index(op.f("ix_lesson_translations_lesson_id"), table_name="lesson_translations")
    op.drop_index(op.f("ix_lesson_translations_created_at"), table_name="lesson_translations")
    op.drop_table("lesson_translations")
    op.drop_index(op.f("ix_xp_events_user_id"), table_name="xp_events")
    op.drop_index(op.f("ix_xp_events_created_at"), table_name="xp_events")
    op.drop_table("xp_events")
    op.drop_index(op.f("ix_user_achievements_user_id"), table_name="user_achievements")
    op.drop_index(op.f("ix_user_achievements_created_at"), table_name="user_achievements")
    op.drop_table("user_achievements")
    op.drop_index(op.f("ix_emergency_contacts_user_id"), table_name="emergency_contacts")
    op.drop_index(op.f("ix_emergency_contacts_created_at"), table_name="emergency_contacts")
    op.drop_table("emergency_contacts")
