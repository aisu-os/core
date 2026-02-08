from fastapi import APIRouter, Depends, HTTPException, status

from aiso_core.dependencies import get_admin_user
from aiso_core.models.user import User
from aiso_core.schemas.app import AppListResponse
from aiso_core.utils.pagination import PaginationParams

router = APIRouter()


@router.get("/review/pending", response_model=AppListResponse)
async def get_pending_reviews(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.post("/review/{app_id}/approve")
async def approve_app(
    app_id: str,
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.post("/review/{app_id}/reject")
async def reject_app(
    app_id: str,
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.post("/apps/{app_id}/suspend")
async def suspend_app(
    app_id: str,
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")
