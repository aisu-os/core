from fastapi import APIRouter, Depends, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import get_db
from aiso_core.schemas.beta_access import BetaAccessRequestResponse
from aiso_core.services.beta_access_service import BetaAccessService

router = APIRouter()


@router.post(
    "/access-request",
    response_model=BetaAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_beta_access_request(
    email: str = Form(...),
    extra_text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    # NOTE(beta): Bu endpoint vaqtinchalik beta early-access flow uchun.
    # Public signup ochilganda ushbu gate olib tashlanadi.
    service = BetaAccessService(db)
    return await service.create_request(email=email, extra_text=extra_text)
