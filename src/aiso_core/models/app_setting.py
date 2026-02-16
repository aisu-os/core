from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class AppSetting(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "app_id", "key", name="uq_app_settings_user_app_key"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    app_id: Mapped[str] = mapped_column(String(100), index=True)
    key: Mapped[str] = mapped_column(String(255))
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB, nullable=True
    )
