from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.user import User
from aiso_core.models.user_session import UserSession
from aiso_core.services.session_service import SessionService


async def _create_user(db_session: AsyncSession, email: str, username: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=username,
        display_name=username,
        hashed_password="$2b$12$dummy_hash_for_test",
        role="user",
        is_active=True,
        cpu=2,
        disk=5120,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_get_session_returns_none_when_not_exists(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "session-none@test.com", "session_none")
    service = SessionService(db_session)

    result = await service.get_session(user.id)

    assert result is None


async def test_save_session_inserts_new_record(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "session-insert@test.com", "session_insert")
    service = SessionService(db_session)

    processes = [{"pid": "p1", "appId": "terminal"}]
    windows = [{"id": "w1", "title": "Terminal"}]
    window_props = {"w1": {"x": 10, "y": 20}}
    extra = {"workspace": "dev"}

    result = await service.save_session(
        user_id=user.id,
        processes=processes,
        windows=windows,
        window_props=window_props,
        next_z_index=101,
        extra=extra,
    )

    assert result.processes == processes
    assert result.windows == windows
    assert result.window_props == window_props
    assert result.next_z_index == 101
    assert result.extra == extra
    assert result.updated_at is not None

    row = await db_session.scalar(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    assert row is not None
    assert row.next_z_index == 101


async def test_save_session_updates_existing_row(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "session-update@test.com", "session_update")
    service = SessionService(db_session)

    await service.save_session(
        user_id=user.id,
        processes=[{"pid": "p1"}],
        windows=[{"id": "w1"}],
        window_props={"w1": {"x": 1}},
        next_z_index=100,
        extra={"v": 1},
    )

    updated = await service.save_session(
        user_id=user.id,
        processes=[{"pid": "p2"}],
        windows=[{"id": "w2"}],
        window_props={"w2": {"x": 2}},
        next_z_index=250,
        extra=None,
    )

    count = await db_session.scalar(
        select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)
    )
    assert count == 1
    assert updated.processes == [{"pid": "p2"}]
    assert updated.windows == [{"id": "w2"}]
    assert updated.window_props == {"w2": {"x": 2}}
    assert updated.next_z_index == 250
    assert updated.extra is None


async def test_delete_session_removes_existing_row(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "session-delete@test.com", "session_delete")
    service = SessionService(db_session)

    await service.save_session(
        user_id=user.id,
        processes=[],
        windows=[],
        window_props={},
        next_z_index=100,
        extra=None,
    )
    await service.delete_session(user.id)

    row = await db_session.scalar(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    assert row is None


async def test_delete_session_is_noop_when_not_exists(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "session-noop@test.com", "session_noop")
    service = SessionService(db_session)

    await service.delete_session(user.id)

    row = await db_session.scalar(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    assert row is None
