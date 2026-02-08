import uuid
from datetime import datetime

from pydantic import BaseModel


class AppVersionCreate(BaseModel):
    version: str
    changelog: str | None = None
    manifest: dict


class AppVersionResponse(BaseModel):
    id: uuid.UUID
    app_id: str
    version: str
    changelog: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
