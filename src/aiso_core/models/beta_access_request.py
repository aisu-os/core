from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class BetaAccessRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "beta_access_requests"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    extra_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
