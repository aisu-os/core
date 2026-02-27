from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.user import User
from aiso_core.models.user_session import UserSession
from aiso_core.utils.security import create_access_token


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


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def _payload(next_z_index: int = 120) -> dict:
    return {
        "processes": [{"pid": "proc-1", "appId": "terminal"}],
        "windows": [{"id": "win-1", "title": "Terminal"}],
        "windowProps": {"win-1": {"x": 12, "y": 24}},
        "nextZIndex": next_z_index,
        "extra": {"workspace": "dev"},
    }


async def test_session_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/session")

    assert response.status_code == 401


async def test_get_session_returns_204_when_absent(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "session-get-empty@test.com", "session_get_empty")

    response = await client.get("/api/v1/session", headers=_auth_headers(user.id))

    assert response.status_code == 204
    assert response.text == ""


async def test_put_then_get_session_returns_saved_data(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "session-save@test.com", "session_save")

    put_response = await client.put(
        "/api/v1/session",
        headers=_auth_headers(user.id),
        json=_payload(next_z_index=150),
    )
    assert put_response.status_code == 200
    put_data = put_response.json()
    assert put_data["window_props"] == {"win-1": {"x": 12, "y": 24}}
    assert put_data["next_z_index"] == 150
    assert put_data["extra"] == {"workspace": "dev"}
    assert put_data["updated_at"]

    get_response = await client.get("/api/v1/session", headers=_auth_headers(user.id))
    assert get_response.status_code == 200
    assert get_response.json()["processes"] == [{"pid": "proc-1", "appId": "terminal"}]


async def test_put_updates_existing_session_without_creating_duplicate(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "session-update-api@test.com", "session_update_api")

    first = _payload(next_z_index=100)
    second = {
        "processes": [{"pid": "proc-2"}],
        "windows": [{"id": "win-2"}],
        "windowProps": {"win-2": {"x": 1}},
        "nextZIndex": 220,
        "extra": None,
    }

    r1 = await client.put("/api/v1/session", headers=_auth_headers(user.id), json=first)
    assert r1.status_code == 200
    r2 = await client.put("/api/v1/session", headers=_auth_headers(user.id), json=second)
    assert r2.status_code == 200
    assert r2.json()["next_z_index"] == 220
    assert r2.json()["extra"] is None

    count = await db_session.scalar(
        select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)
    )
    assert count == 1


async def test_delete_session_clears_data_and_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "session-delete-api@test.com", "session_delete_api")

    await client.put("/api/v1/session", headers=_auth_headers(user.id), json=_payload())

    delete1 = await client.delete("/api/v1/session", headers=_auth_headers(user.id))
    assert delete1.status_code == 204

    get_after_delete = await client.get("/api/v1/session", headers=_auth_headers(user.id))
    assert get_after_delete.status_code == 204

    delete2 = await client.delete("/api/v1/session", headers=_auth_headers(user.id))
    assert delete2.status_code == 204


async def test_session_is_isolated_between_users(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_a = await _create_user(db_session, "session-a@test.com", "session_a")
    user_b = await _create_user(db_session, "session-b@test.com", "session_b")

    put = await client.put("/api/v1/session", headers=_auth_headers(user_a.id), json=_payload())
    assert put.status_code == 200

    b_get = await client.get("/api/v1/session", headers=_auth_headers(user_b.id))
    assert b_get.status_code == 204

    a_get = await client.get("/api/v1/session", headers=_auth_headers(user_a.id))
    assert a_get.status_code == 200
