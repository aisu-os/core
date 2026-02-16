from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import get_db
from aiso_core.dependencies import get_current_user
from aiso_core.models.user import User
from aiso_core.schemas.app_setting import (
    AppSettingResponse,
    AppSettingsListResponse,
    SetAppSettingRequest,
)
from aiso_core.services.app_setting_service import AppSettingService

router = APIRouter()


@router.get("/{app_id}", response_model=AppSettingsListResponse)
async def get_app_settings(
    app_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppSettingsListResponse:
    service = AppSettingService(db)
    return await service.get_all(current_user.id, app_id)


@router.get("/{app_id}/{key}", response_model=AppSettingResponse)
async def get_setting(
    app_id: str,
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppSettingResponse:
    service = AppSettingService(db)
    return await service.get_one(current_user.id, app_id, key)


@router.put(
    "/{app_id}/{key}",
    response_model=AppSettingResponse,
    status_code=status.HTTP_200_OK,
)
async def set_setting(
    app_id: str,
    key: str,
    data: SetAppSettingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppSettingResponse:
    service = AppSettingService(db)
    return await service.set_value(current_user.id, app_id, key, data.value)


@router.delete("/{app_id}/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    app_id: str,
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AppSettingService(db)
    await service.delete_one(current_user.id, app_id, key)
