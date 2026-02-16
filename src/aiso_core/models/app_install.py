from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class AppInstall(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "app_installs"
    __table_args__ = (UniqueConstraint("app_id", "user_id"),)

    app_id: Mapped[str] = mapped_column(String(100), ForeignKey("apps.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(20))

    # Relationships
    app: Mapped[App] = relationship(back_populates="installs")  # noqa: F821
