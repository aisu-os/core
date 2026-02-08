from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class AppInstall(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "app_installs"
    __table_args__ = (UniqueConstraint("app_id", "user_id"),)

    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[str] = mapped_column(String(20))

    # Relationships
    app: Mapped[App] = relationship(back_populates="installs")  # noqa: F821
    user: Mapped[User] = relationship(back_populates="installs")  # noqa: F821
