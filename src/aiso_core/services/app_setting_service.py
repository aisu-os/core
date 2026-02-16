from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.app_setting import AppSetting
from aiso_core.schemas.app_setting import AppSettingResponse, AppSettingsListResponse


class AppSettingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(
        self, user_id: uuid.UUID, app_id: str
    ) -> AppSettingsListResponse:
        stmt = select(AppSetting).where(
            and_(
                AppSetting.user_id == user_id,
                AppSetting.app_id == app_id,
            )
        )
        result = await self.db.execute(stmt)
        settings = result.scalars().all()

        return AppSettingsListResponse(
            app_id=app_id,
            settings=[
                AppSettingResponse(
                    app_id=s.app_id,
                    key=s.key,
                    value=s.value,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in settings
            ],
            total=len(settings),
        )

    async def get_one(
        self, user_id: uuid.UUID, app_id: str, key: str
    ) -> AppSettingResponse:
        stmt = select(AppSetting).where(
            and_(
                AppSetting.user_id == user_id,
                AppSetting.app_id == app_id,
                AppSetting.key == key,
            )
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Setting not found: {app_id}/{key}",
            )

        return AppSettingResponse(
            app_id=setting.app_id,
            key=setting.key,
            value=setting.value,
            created_at=setting.created_at,
            updated_at=setting.updated_at,
        )

    async def set_value(
        self, user_id: uuid.UUID, app_id: str, key: str, value: Any
    ) -> AppSettingResponse:
        stmt = select(AppSetting).where(
            and_(
                AppSetting.user_id == user_id,
                AppSetting.app_id == app_id,
                AppSetting.key == key,
            )
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
        else:
            setting = AppSetting(
                user_id=user_id,
                app_id=app_id,
                key=key,
                value=value,
            )
            self.db.add(setting)

        await self.db.flush()
        await self.db.refresh(setting)

        return AppSettingResponse(
            app_id=setting.app_id,
            key=setting.key,
            value=setting.value,
            created_at=setting.created_at,
            updated_at=setting.updated_at,
        )

    async def delete_one(
        self, user_id: uuid.UUID, app_id: str, key: str
    ) -> None:
        stmt = select(AppSetting).where(
            and_(
                AppSetting.user_id == user_id,
                AppSetting.app_id == app_id,
                AppSetting.key == key,
            )
        )
        result = await self.db.execute(stmt)
        setting = result.scalar_one_or_none()

        if setting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Setting not found: {app_id}/{key}",
            )

        await self.db.delete(setting)
        await self.db.flush()
