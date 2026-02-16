from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Request schemas ──


class SetAppSettingRequest(BaseModel):
    value: Any = Field(..., description="Any JSON-serializable value")


# ── Response schemas ──


class AppSettingResponse(BaseModel):
    app_id: str
    key: str
    value: Any
    created_at: datetime
    updated_at: datetime


class AppSettingsListResponse(BaseModel):
    app_id: str
    settings: list[AppSettingResponse]
    total: int
