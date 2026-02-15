"""make user wallpaper nullable

Revision ID: 7d2c9f1a3b4e
Revises: 5ef8abdb6a17
Create Date: 2026-02-10 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d2c9f1a3b4e"
down_revision: str | None = "5ef8abdb6a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "wallpaper",
        existing_type=sa.String(length=500),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE users SET wallpaper='default.jpg' WHERE wallpaper IS NULL")
    op.alter_column(
        "users",
        "wallpaper",
        existing_type=sa.String(length=500),
        nullable=False,
    )
