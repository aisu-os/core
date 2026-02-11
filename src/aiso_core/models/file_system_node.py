from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiso_core.models.base import Base, TimestampMixin, UUIDMixin


class FileSystemNode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "file_system_nodes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_system_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    original_path: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    trashed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    parent: Mapped[FileSystemNode | None] = relationship(
        back_populates="children",
        remote_side="FileSystemNode.id",
    )
    children: Mapped[list[FileSystemNode]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "path", name="uq_user_path"),
        Index("ix_user_parent", "user_id", "parent_id"),
        Index("ix_user_trashed", "user_id", "is_trashed"),
        CheckConstraint("node_type IN ('file', 'directory')", name="ck_node_type"),
    )
