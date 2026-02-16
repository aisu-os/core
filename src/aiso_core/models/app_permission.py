from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, UUIDMixin


class AppPermission(Base, UUIDMixin):
    __tablename__ = "app_permissions"
    __table_args__ = (UniqueConstraint("app_id", "user_id", "permission"),)

    app_id: Mapped[str] = mapped_column(String(100), ForeignKey("apps.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(200))
    granted: Mapped[bool] = mapped_column(Boolean)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    app: Mapped[App] = relationship(back_populates="permissions")  # noqa: F821
