from datetime import datetime

from pydantic import BaseModel

from aiso_core.schemas.common import PaginatedResponse


class AuthorInfo(BaseModel):
    name: str
    github: str | None = None

    model_config = {"from_attributes": True}


class AppCreate(BaseModel):
    id: str
    name: str
    description: str | None = None
    long_description: str | None = None
    category: str
    tags: list[str] | None = None
    manifest: dict
    current_version: str


class AppUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    long_description: str | None = None
    category: str | None = None
    tags: list[str] | None = None


class AppResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    icon_url: str | None = None
    category: str
    current_version: str
    rating_avg: float
    review_count: int
    install_count: int
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppDetailResponse(AppResponse):
    long_description: str | None = None
    tags: list[str] | None = None
    entry_url: str | None = None
    manifest: dict
    created_at: datetime


class AppListResponse(PaginatedResponse):
    apps: list[AppResponse]
