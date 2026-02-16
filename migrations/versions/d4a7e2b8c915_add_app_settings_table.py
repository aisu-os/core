"""add app_settings table

Revision ID: d4a7e2b8c915
Revises: c3e59b0f4a12
Create Date: 2026-02-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4a7e2b8c915"
down_revision: str | None = "c3e59b0f4a12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "app_id", "key", name="uq_app_settings_user_app_key"),
    )
    op.create_index(
        op.f("ix_app_settings_user_id"),
        "app_settings",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_settings_app_id"),
        "app_settings",
        ["app_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_app_settings_app_id"), table_name="app_settings")
    op.drop_index(op.f("ix_app_settings_user_id"), table_name="app_settings")
    op.drop_table("app_settings")
