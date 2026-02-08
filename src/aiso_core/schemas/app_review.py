import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = None
    comment: str | None = None


class ReviewResponse(BaseModel):
    id: uuid.UUID
    app_id: str
    user_id: uuid.UUID
    rating: int
    title: str | None = None
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
