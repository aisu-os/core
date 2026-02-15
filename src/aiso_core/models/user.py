from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    cpu: Mapped[int] = mapped_column(Integer, default=2)
    disk: Mapped[int] = mapped_column(Integer, default=5120)
    wallpaper: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)

    # Relationships
    container: Mapped[UserContainer | None] = relationship(  # noqa: F821
        back_populates="user",
        uselist=False,
    )
