from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.data.system_apps import SYSTEM_APPS
from aiso_core.models.app import App
from aiso_core.models.app_install import AppInstall
from aiso_core.models.app_permission import AppPermission
from aiso_core.models.user import User

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
SYSTEM_USER_EMAIL = "system@aisu.internal"
SYSTEM_USER_USERNAME = "system"


class SystemAppService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_system_user(self) -> User:
        """Check if system user exists, create if not."""
        user = await self.db.get(User, SYSTEM_USER_ID)
        if user is not None:
            return user

        user = User(
            id=SYSTEM_USER_ID,
            email=SYSTEM_USER_EMAIL,
            username=SYSTEM_USER_USERNAME,
            display_name="Aisu System",
            hashed_password="!disabled",
            role="system",
            is_active=False,
            cpu=0,
            disk=0,
        )
        self.db.add(user)
        await self.db.flush()
        logger.info("Created system user: %s", SYSTEM_USER_ID)
        return user

    async def seed_system_apps(self) -> int:
        """Seed system apps into the database. Idempotent."""
        system_user = await self.ensure_system_user()
        created = 0

        for app_data in SYSTEM_APPS:
            existing = await self.db.get(App, app_data["id"])
            if existing is not None:
                existing.name = app_data["name"]
                existing.description = app_data["description"]
                existing.manifest = app_data["manifest"]
                existing.current_version = app_data["current_version"]
                existing.is_system = True
                existing.status = "approved"
                logger.info("Updated system app: %s", app_data["id"])
                continue

            app = App(
                id=app_data["id"],
                name=app_data["name"],
                description=app_data["description"],
                author_id=system_user.id,
                category=app_data["category"],
                tags=app_data.get("tags"),
                manifest=app_data["manifest"],
                current_version=app_data["current_version"],
                install_count=0,
                rating_avg=0,
                review_count=0,
                status="approved",
                is_system=True,
            )
            self.db.add(app)
            created += 1
            logger.info("Created system app: %s", app_data["id"])

        await self.db.flush()
        return created

    async def install_system_apps_for_user(self, user_id: uuid.UUID) -> int:
        """Install system apps for a user. Idempotent."""
        installed = 0
        now = datetime.now(UTC)

        for app_data in SYSTEM_APPS:
            app_id: str = app_data["id"]

            stmt = select(AppInstall).where(
                AppInstall.app_id == app_id,
                AppInstall.user_id == user_id,
            )
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none() is not None:
                continue

            install = AppInstall(
                app_id=app_id,
                user_id=user_id,
                version=app_data["current_version"],
            )
            self.db.add(install)

            for perm_key in app_data.get("permissions", []):
                permission = AppPermission(
                    app_id=app_id,
                    user_id=user_id,
                    permission=perm_key,
                    granted=True,
                    granted_at=now,
                )
                self.db.add(permission)

            installed += 1

        await self.db.flush()
        logger.info("Installed %d system apps for user %s", installed, user_id)
        return installed
