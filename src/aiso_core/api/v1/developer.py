from fastapi import APIRouter, Depends, HTTPException, status

from aiso_core.dependencies import get_developer_user
from aiso_core.models.user import User
from aiso_core.schemas.app import AppCreate, AppDetailResponse, AppListResponse, AppUpdate
from aiso_core.schemas.app_version import AppVersionCreate, AppVersionResponse
from aiso_core.utils.pagination import PaginationParams

router = APIRouter()


@router.post("/apps", response_model=AppDetailResponse, status_code=201)
async def create_app(
    data: AppCreate,
    current_user: User = Depends(get_developer_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.put("/apps/{app_id}", response_model=AppDetailResponse)
async def update_app(
    app_id: str,
    data: AppUpdate,
    current_user: User = Depends(get_developer_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.get("/apps", response_model=AppListResponse)
async def get_my_apps(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_developer_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.get("/apps/{app_id}/stats")
async def get_app_stats(
    app_id: str,
    current_user: User = Depends(get_developer_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.post("/apps/{app_id}/versions", response_model=AppVersionResponse, status_code=201)
async def create_version(
    app_id: str,
    data: AppVersionCreate,
    current_user: User = Depends(get_developer_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")
