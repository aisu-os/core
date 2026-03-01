from fastapi import APIRouter
from sqlalchemy import text

from aiso_core.config import settings
from aiso_core.database import async_session_factory
from aiso_core.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"

    status = "ok" if db_status == "ok" else "degraded"

    return HealthResponse(
        status=status,
        version=settings.app_version,
        database=db_status,
    )
