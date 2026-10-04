"""accounts knowledge feedback

Revision ID: 0002
Revises: 0001

Adds: auth_tokens (email verification / password reset), users.email_verified,
users.tokens_valid_after, knowledge_documents (RAG document tracking), analysis_feedback.
Create Date: 2026-10-01 12:04:57.704589+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("doc_key", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("topic", sa.String(length=40), nullable=False),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("chunks", sa.Integer(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("doc_key", name=op.f("uq_knowledge_documents_doc_key")),
    )
    op.create_index(op.f("ix_knowledge_documents_created_at"), "knowledge_documents", ["created_at"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_status"), "knowledge_documents", ["status"], unique=False)
    op.create_table(
        "auth_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_auth_tokens_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_tokens_token_hash")),
    )
    op.create_index(op.f("ix_auth_tokens_created_at"), "auth_tokens", ["created_at"], unique=False)
    op.create_index(op.f("ix_auth_tokens_user_id"), "auth_tokens", ["user_id"], unique=False)
    op.create_table(
        "analysis_feedback",
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=10), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("share_text", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["scam_analyses.id"], name=op.f("fk_analysis_feedback_analysis_id_scam_analyses"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_analysis_feedback_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_feedback")),
        sa.UniqueConstraint("analysis_id", "user_id", name="uq_analysis_feedback_analysis_user"),
    )
    op.create_index(op.f("ix_analysis_feedback_analysis_id"), "analysis_feedback", ["analysis_id"], unique=False)
    op.create_index(op.f("ix_analysis_feedback_created_at"), "analysis_feedback", ["created_at"], unique=False)
    op.create_index(op.f("ix_analysis_feedback_user_id"), "analysis_feedback", ["user_id"], unique=False)
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True))
    # Google accounts were verified by Google at sign-up.
    op.execute("UPDATE users SET email_verified = true, email_verified_at = now() WHERE auth_provider = 'google'")


def downgrade() -> None:
    op.drop_column("users", "tokens_valid_after")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
    op.drop_index(op.f("ix_analysis_feedback_user_id"), table_name="analysis_feedback")
    op.drop_index(op.f("ix_analysis_feedback_created_at"), table_name="analysis_feedback")
    op.drop_index(op.f("ix_analysis_feedback_analysis_id"), table_name="analysis_feedback")
    op.drop_table("analysis_feedback")
    op.drop_index(op.f("ix_auth_tokens_user_id"), table_name="auth_tokens")
    op.drop_index(op.f("ix_auth_tokens_created_at"), table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_index(op.f("ix_knowledge_documents_status"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_created_at"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
