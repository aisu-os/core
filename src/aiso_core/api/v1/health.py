from fastapi import APIRouter

from aiso_core.config import settings
from aiso_core.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version=settings.app_version)
