from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class AppVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "app_versions"
    __table_args__ = (UniqueConstraint("app_id", "version"),)

    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id"))
    version: Mapped[str] = mapped_column(String(20))
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict] = mapped_column(JSONB)
    bundle_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # Relationships
    app: Mapped[App] = relationship(back_populates="versions")  # noqa: F821
