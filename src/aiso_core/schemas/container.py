import uuid
from datetime import datetime

from pydantic import BaseModel


class ContainerStatusResponse(BaseModel):
    user_id: uuid.UUID
    container_name: str
    container_id: str | None = None
    container_ip: str | None = None
    status: str
    cpu_limit: int
    ram_limit: int
    disk_limit: int
    network_rate: str
    started_at: datetime | None = None
    last_activity: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContainerActionResponse(BaseModel):
    status: str
    message: str


class ContainerEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
