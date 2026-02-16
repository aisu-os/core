from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin


class App(Base, TimestampMixin):
    __tablename__ = "apps"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), index=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    entry_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_version: Mapped[str] = mapped_column(String(20))
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    versions: Mapped[list[AppVersion]] = relationship(back_populates="app")  # noqa: F821
    installs: Mapped[list[AppInstall]] = relationship(back_populates="app")  # noqa: F821
    screenshots: Mapped[list[AppScreenshot]] = relationship(back_populates="app")  # noqa: F821
    reviews: Mapped[list[AppReview]] = relationship(back_populates="app")  # noqa: F821
    permissions: Mapped[list[AppPermission]] = relationship(back_populates="app")  # noqa: F821
