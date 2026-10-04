"""user state

Revision ID: 0005
Revises: 0004

Adds users.state (Indian state / union territory, chosen from a dropdown at sign-up).
Create Date: 2026-10-04 08:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("state", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "state")
