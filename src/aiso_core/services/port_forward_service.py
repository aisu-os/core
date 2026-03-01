import logging
import random
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.models.port_forward import PortForward
from aiso_core.models.user_container import UserContainer
from aiso_core.schemas.port_forward import PortForwardListResponse, PortForwardResponse
from aiso_core.services.caddy_service import CaddyError, CaddyService

logger = logging.getLogger(__name__)

MAX_FORWARDS = 3

_ADJECTIVES = ["swift", "calm", "bold", "warm", "cool", "fast", "keen", "neat"]
_NOUNS = ["fox", "owl", "elk", "ray", "bee", "ant", "ram", "cod"]


def _generate_random_subdomain() -> str:
    adj = random.choice(_ADJECTIVES)  # noqa: S311
    noun = random.choice(_NOUNS)  # noqa: S311
    num = random.randint(100, 999)  # noqa: S311
    return f"{adj}-{noun}-{num}"


class PortForwardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_forwards(self, user_id: uuid.UUID) -> PortForwardListResponse:
        stmt = (
            select(PortForward)
            .where(PortForward.user_id == user_id)
            .order_by(PortForward.created_at.desc())
        )
        result = await self.db.execute(stmt)
        forwards = list(result.scalars().all())

        return PortForwardListResponse(
            forwards=[self._to_response(f) for f in forwards],
            total=len(forwards),
        )

    async def create_forward(
        self,
        user_id: uuid.UUID,
        container_port: int,
        subdomain: str | None,
    ) -> PortForwardResponse:
        # 1. Check forward limit
        count_stmt = select(PortForward).where(PortForward.user_id == user_id)
        result = await self.db.execute(count_stmt)
        existing = list(result.scalars().all())
        if len(existing) >= MAX_FORWARDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Maximum {MAX_FORWARDS} port forwards allowed",
            )

        # 2. Check port is not already in use
        if any(f.container_port == container_port for f in existing):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Port {container_port} is already forwarded",
            )

        # 3. Prepare subdomain
        if subdomain is None:
            subdomain = _generate_random_subdomain()

        # 4. Check subdomain uniqueness
        sub_stmt = select(PortForward).where(PortForward.subdomain == subdomain)
        sub_result = await self.db.execute(sub_stmt)
        if sub_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This subdomain is already taken",
            )

        # 5. Get container IP
        container_stmt = select(UserContainer).where(UserContainer.user_id == user_id)
        container_result = await self.db.execute(container_stmt)
        container = container_result.scalar_one_or_none()

        if container is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Container not found",
            )

        if container.status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Container is not running",
            )

        # 6. Save to DB
        forward = PortForward(
            user_id=user_id,
            subdomain=subdomain,
            container_port=container_port,
            container_ip=container.container_ip,
            protocol="http",
            status="active",
        )
        self.db.add(forward)
        await self.db.flush()
        await self.db.refresh(forward)

        # 7. Add Caddy route
        caddy = CaddyService()
        upstream = f"{container.container_ip}:{container_port}"
        try:
            await caddy.add_route(subdomain, upstream)
        except CaddyError:
            logger.warning("Failed to add Caddy route: %s", subdomain, exc_info=True)

        return self._to_response(forward)

    async def get_forward(
        self, user_id: uuid.UUID, forward_id: uuid.UUID
    ) -> PortForwardResponse:
        forward = await self._get_user_forward(user_id, forward_id)
        return self._to_response(forward)

    async def delete_forward(
        self, user_id: uuid.UUID, forward_id: uuid.UUID
    ) -> None:
        forward = await self._get_user_forward(user_id, forward_id)

        # Remove Caddy route
        caddy = CaddyService()
        try:
            await caddy.remove_route(forward.subdomain)
        except CaddyError:
            logger.warning("Failed to remove Caddy route: %s", forward.subdomain, exc_info=True)

        await self.db.delete(forward)

    async def _get_user_forward(
        self, user_id: uuid.UUID, forward_id: uuid.UUID
    ) -> PortForward:
        stmt = select(PortForward).where(
            PortForward.id == forward_id,
            PortForward.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        forward = result.scalar_one_or_none()
        if forward is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Port forward not found",
            )
        return forward

    @staticmethod
    def _to_response(forward: PortForward) -> PortForwardResponse:
        return PortForwardResponse(
            id=forward.id,
            subdomain=forward.subdomain,
            url=f"{settings.port_forward_scheme}://{forward.subdomain}.{settings.port_forward_domain}",
            container_port=forward.container_port,
            protocol=forward.protocol,
            status=forward.status,
            created_at=forward.created_at,
            request_count=0,
            last_request_at=None,
        )
