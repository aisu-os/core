from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class AppReview(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "app_reviews"
    __table_args__ = (
        UniqueConstraint("app_id", "user_id"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
    )

    app_id: Mapped[str] = mapped_column(String(100), ForeignKey("apps.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    app: Mapped[App] = relationship(back_populates="reviews")  # noqa: F821
