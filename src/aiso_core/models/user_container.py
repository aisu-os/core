from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class UserContainer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_containers"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    container_name: Mapped[str] = mapped_column(String(200), unique=True)
    container_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="creating"
    )  # creating | running | paused | stopped | removed | error
    cpu_limit: Mapped[int] = mapped_column(BigInteger, default=2)
    ram_limit: Mapped[int] = mapped_column(BigInteger, default=2_147_483_648)  # 2GB in bytes
    disk_limit: Mapped[int] = mapped_column(BigInteger, default=5_368_709_120)  # 5GB in bytes
    network_rate: Mapped[str] = mapped_column(String(20), default="5mbit")
    last_activity: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship(  # noqa: F821
        back_populates="container",
    )
