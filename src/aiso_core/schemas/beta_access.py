import uuid
from datetime import datetime

from pydantic import BaseModel


class BetaAccessRequestResponse(BaseModel):
    request_id: uuid.UUID
    message: str
    token_expires_at: datetime
