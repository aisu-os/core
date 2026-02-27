from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.user_session import UserSession
from aiso_core.schemas.session import SessionResponse


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_session(self, user_id: uuid.UUID) -> SessionResponse | None:
        stmt = select(UserSession).where(UserSession.user_id == user_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session is None:
            return None

        return SessionResponse(
            processes=session.processes,
            windows=session.windows,
            window_props=session.window_props,
            next_z_index=session.next_z_index,
            extra=session.extra,
            updated_at=session.updated_at,
        )

    async def save_session(
        self,
        user_id: uuid.UUID,
        processes: list[dict[str, Any]],
        windows: list[dict[str, Any]],
        window_props: dict[str, dict[str, Any]],
        next_z_index: int,
        extra: dict[str, Any] | None,
    ) -> SessionResponse:
        stmt = select(UserSession).where(UserSession.user_id == user_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            session.processes = processes
            session.windows = windows
            session.window_props = window_props
            session.next_z_index = next_z_index
            session.extra = extra
        else:
            session = UserSession(
                user_id=user_id,
                processes=processes,
                windows=windows,
                window_props=window_props,
                next_z_index=next_z_index,
                extra=extra,
            )
            self.db.add(session)

        await self.db.flush()
        await self.db.refresh(session)

        return SessionResponse(
            processes=session.processes,
            windows=session.windows,
            window_props=session.window_props,
            next_z_index=session.next_z_index,
            extra=session.extra,
            updated_at=session.updated_at,
        )

    async def delete_session(self, user_id: uuid.UUID) -> None:
        stmt = select(UserSession).where(UserSession.user_id == user_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session:
            await self.db.delete(session)
            await self.db.flush()
