from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aiso_core.models.base import Base, UUIDMixin


class AppPermission(Base, UUIDMixin):
    __tablename__ = "app_permissions"
    __table_args__ = (UniqueConstraint("app_id", "user_id", "permission"),)

    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    permission: Mapped[str] = mapped_column(String(200))
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
