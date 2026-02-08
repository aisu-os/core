from __future__ import annotations

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class AppScreenshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "app_screenshots"

    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id"))
    url: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Relationships
    app: Mapped[App] = relationship(back_populates="screenshots")  # noqa: F821
