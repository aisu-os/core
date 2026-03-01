import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

RESERVED_SUBDOMAINS = {
    "www", "api", "admin", "mail", "ftp", "ssh",
    "cdn", "ns1", "ns2", "test", "dev", "staging",
    "app", "dashboard", "panel", "control",
}

_SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class CreatePortForwardRequest(BaseModel):
    container_port: int = Field(ge=1024, le=65535)
    subdomain: str | None = Field(None, min_length=3, max_length=32)

    @field_validator("subdomain")
    @classmethod
    def validate_subdomain(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _SUBDOMAIN_RE.match(v):
            raise ValueError("Only lowercase letters, numbers, and hyphens are allowed")
        if "--" in v:
            raise ValueError("Consecutive hyphens are not allowed")
        if v in RESERVED_SUBDOMAINS:
            raise ValueError("This subdomain is reserved")
        return v


class PortForwardResponse(BaseModel):
    id: uuid.UUID
    subdomain: str
    url: str
    container_port: int
    protocol: str
    status: str
    created_at: datetime
    request_count: int = 0
    last_request_at: datetime | None = None

    model_config = {"from_attributes": True}


class PortForwardListResponse(BaseModel):
    forwards: list[PortForwardResponse]
    total: int
