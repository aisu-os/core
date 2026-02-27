from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class UserSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    processes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    windows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    window_props: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    next_z_index: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    extra: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
