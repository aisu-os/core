from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class ErrorResponse(BaseModel):
    detail: str


class PaginatedResponse(BaseModel):
    total: int
    page: int
    per_page: int
