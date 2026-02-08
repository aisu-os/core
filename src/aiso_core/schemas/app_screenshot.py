import uuid

from pydantic import BaseModel


class ScreenshotResponse(BaseModel):
    id: uuid.UUID
    app_id: str
    url: str
    sort_order: int

    model_config = {"from_attributes": True}
