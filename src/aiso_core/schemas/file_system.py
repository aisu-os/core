from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

# ── Deterministic UUID generator ──

_FS_NAMESPACE = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


def path_to_uuid(user_id: uuid.UUID, path: str) -> uuid.UUID:
    """user_id va path asosida barqaror UUID yaratadi."""
    return uuid.uuid5(_FS_NAMESPACE, f"{user_id}:{path}")


# ── Request schemas ──


class CreateNodeRequest(BaseModel):
    parent_path: str
    name: str = Field(max_length=255)
    node_type: str = Field(pattern=r"^(file|directory)$")
    mime_type: str | None = None
    size: int = 0


class RenameNodeRequest(BaseModel):
    path: str
    new_name: str = Field(max_length=255)


class MoveNodeRequest(BaseModel):
    source_path: str
    dest_parent_path: str


class CopyNodeRequest(BaseModel):
    source_path: str
    dest_parent_path: str


class DeleteNodeRequest(BaseModel):
    path: str
    permanent: bool = False


class RestoreNodeRequest(BaseModel):
    path: str


class BulkDeleteRequest(BaseModel):
    paths: list[str]
    permanent: bool = False


class BulkMoveRequest(BaseModel):
    source_paths: list[str]
    dest_parent_path: str


class DesktopPositionItem(BaseModel):
    path: str
    x: int
    y: int


class BatchUpdateDesktopPositionsRequest(BaseModel):
    positions: list[DesktopPositionItem]


# ── Response schemas ──


class FileNodeResponse(BaseModel):
    id: uuid.UUID
    name: str
    path: str
    node_type: str
    mime_type: str | None = None
    size: int = 0
    is_trashed: bool = False
    original_path: str | None = None
    trashed_at: datetime | None = None
    desktop_x: int | None = None
    desktop_y: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FileNodeWithChildrenResponse(FileNodeResponse):
    children: list[FileNodeResponse] = []


class FileNodeTreeResponse(FileNodeResponse):
    children: list[FileNodeTreeResponse] = []


class DirectoryListingResponse(BaseModel):
    path: str
    node: FileNodeResponse
    children: list[FileNodeResponse]
    total: int


class MoveResultResponse(BaseModel):
    old_path: str
    new_path: str
    node: FileNodeResponse


class CopyResultResponse(BaseModel):
    source_path: str
    new_path: str
    node: FileNodeResponse


class BulkResultItem(BaseModel):
    path: str
    error: str | None = None


class BulkResultResponse(BaseModel):
    succeeded: list[str]
    failed: list[BulkResultItem]


# ── File content schemas ──


class ReadFileResponse(BaseModel):
    content: str
    size: int
    encoding: str = "utf-8"


class WriteFileRequest(BaseModel):
    path: str
    content: str


class WriteFileResponse(BaseModel):
    path: str
    size: int
    updated_at: datetime
