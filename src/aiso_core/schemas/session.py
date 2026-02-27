from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SaveSessionRequest(BaseModel):
    processes: list[dict[str, Any]]
    windows: list[dict[str, Any]]
    window_props: dict[str, dict[str, Any]] = Field(alias="windowProps")
    next_z_index: int = Field(alias="nextZIndex")
    extra: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class SessionResponse(BaseModel):
    processes: list[dict[str, Any]]
    windows: list[dict[str, Any]]
    window_props: dict[str, dict[str, Any]]
    next_z_index: int
    extra: dict[str, Any] | None
    updated_at: datetime

    model_config = {"from_attributes": True}
