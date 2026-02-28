from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class PortForward(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "port_forwards"
    __table_args__ = (
        UniqueConstraint("user_id", "container_port", name="uq_user_container_port"),
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    subdomain: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    container_port: Mapped[int] = mapped_column(Integer)
    container_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    protocol: Mapped[str] = mapped_column(String(10), default="http")
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Relationships
    user: Mapped[User] = relationship()  # noqa: F821
