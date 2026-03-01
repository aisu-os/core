"""Port Forward API and service tests."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.models.port_forward import PortForward
from aiso_core.models.user import User
from aiso_core.models.user_container import UserContainer
from aiso_core.utils.security import create_access_token


# ── Helpers ──


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_user(db: AsyncSession, username: str = "testuser") -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{username}@test.com",
        username=username,
        display_name=username,
        hashed_password="$2b$12$dummy_hash_for_test",
        role="user",
        is_active=True,
        cpu=2,
        disk=5120,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_container(
    db: AsyncSession,
    user_id: uuid.UUID,
    status: str = "running",
    container_ip: str = "172.20.0.10",
) -> UserContainer:
    container = UserContainer(
        id=uuid.uuid4(),
        user_id=user_id,
        container_name=f"aisu_{user_id}",
        container_id="abc123",
        container_ip=container_ip,
        status=status,
    )
    db.add(container)
    await db.commit()
    await db.refresh(container)
    return container


async def _create_forward(
    db: AsyncSession,
    user_id: uuid.UUID,
    subdomain: str = "myapp",
    container_port: int = 3000,
    container_ip: str = "172.20.0.10",
) -> PortForward:
    forward = PortForward(
        id=uuid.uuid4(),
        user_id=user_id,
        subdomain=subdomain,
        container_port=container_port,
        container_ip=container_ip,
        protocol="http",
        status="active",
    )
    db.add(forward)
    await db.commit()
    await db.refresh(forward)
    return forward


# ── Config Endpoint ──


class TestConfigEndpoint:
    async def test_returns_domain_and_scheme(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/port-forwards/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "t.localhost"
        assert data["scheme"] == "http"


# ── List Forwards ──


class TestListForwards:
    async def test_empty_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        resp = await client.get(
            "/api/v1/port-forwards", headers=_auth_headers(user.id)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["forwards"] == []
        assert data["total"] == 0

    async def test_returns_user_forwards(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_forward(db_session, user.id, "app1", 3000)
        await _create_forward(db_session, user.id, "app2", 8080)

        resp = await client.get(
            "/api/v1/port-forwards", headers=_auth_headers(user.id)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        subdomains = {f["subdomain"] for f in data["forwards"]}
        assert subdomains == {"app1", "app2"}

    async def test_url_uses_config_domain(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_forward(db_session, user.id, "myapp", 3000)

        resp = await client.get(
            "/api/v1/port-forwards", headers=_auth_headers(user.id)
        )
        url = resp.json()["forwards"][0]["url"]
        assert url == "http://myapp.t.localhost"

    async def test_does_not_return_other_users_forwards(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user1 = await _create_user(db_session, "user1")
        user2 = await _create_user(db_session, "user2")
        await _create_forward(db_session, user1.id, "app1", 3000)
        await _create_forward(db_session, user2.id, "app2", 4000)

        resp = await client.get(
            "/api/v1/port-forwards", headers=_auth_headers(user1.id)
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["forwards"][0]["subdomain"] == "app1"

    async def test_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/port-forwards")
        assert resp.status_code in (401, 403)


# ── Create Forward ──


class TestCreateForward:
    @pytest.fixture(autouse=True)
    def _enable_container(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "container_enabled", True)

    async def test_create_with_subdomain(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_container(db_session, user.id)

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000, "subdomain": "myapp"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["subdomain"] == "myapp"
        assert data["container_port"] == 3000
        assert data["url"] == "http://myapp.t.localhost"
        assert data["status"] == "active"
        assert data["protocol"] == "http"

    async def test_create_without_subdomain_generates_random(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_container(db_session, user.id)

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000},
        )
        assert resp.status_code == 201
        subdomain = resp.json()["subdomain"]
        # Should be in adj-noun-NNN format
        parts = subdomain.split("-")
        assert len(parts) == 3
        assert parts[2].isdigit()

    async def test_create_saves_to_db(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_container(db_session, user.id)

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 5000, "subdomain": "dbtest"},
        )
        assert resp.status_code == 201

        result = await db_session.execute(
            select(PortForward).where(PortForward.subdomain == "dbtest")
        )
        forward = result.scalar_one()
        assert forward.container_port == 5000
        assert forward.container_ip == "172.20.0.10"
        assert forward.user_id == user.id

    async def test_duplicate_port_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_container(db_session, user.id)
        await _create_forward(db_session, user.id, "existing", 3000)

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000, "subdomain": "another"},
        )
        assert resp.status_code == 409
        assert "3000" in resp.json()["detail"]

    async def test_duplicate_subdomain_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user1 = await _create_user(db_session, "user1")
        user2 = await _create_user(db_session, "user2")
        await _create_container(db_session, user1.id, container_ip="172.20.0.10")
        await _create_container(db_session, user2.id, container_ip="172.20.0.11")
        await _create_forward(db_session, user1.id, "taken", 3000)

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user2.id),
            json={"container_port": 4000, "subdomain": "taken"},
        )
        assert resp.status_code == 409
        assert "subdomain" in resp.json()["detail"]

    async def test_max_3_limit(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_container(db_session, user.id)
        await _create_forward(db_session, user.id, "a1", 3001)
        await _create_forward(db_session, user.id, "a2", 3002)
        await _create_forward(db_session, user.id, "a3", 3003)

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3004, "subdomain": "test-app"},
        )
        assert resp.status_code == 429
        assert "3" in resp.json()["detail"]

    async def test_container_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        # We don't create a container

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000},
        )
        assert resp.status_code == 404
        assert "Container" in resp.json()["detail"]

    async def test_container_not_running(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        await _create_container(db_session, user.id, status="stopped")

        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000},
        )
        assert resp.status_code == 409
        assert "not running" in resp.json()["detail"]

    async def test_port_below_1024_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 80},
        )
        assert resp.status_code == 422

    async def test_port_above_65535_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 70000},
        )
        assert resp.status_code == 422

    async def test_reserved_subdomain_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000, "subdomain": "admin"},
        )
        assert resp.status_code == 422

    async def test_invalid_subdomain_format_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        resp = await client.post(
            "/api/v1/port-forwards",
            headers=_auth_headers(user.id),
            json={"container_port": 3000, "subdomain": "UPPER-case"},
        )
        assert resp.status_code == 422


# ── Get Forward ──


class TestGetForward:
    async def test_get_own_forward(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        forward = await _create_forward(db_session, user.id)

        resp = await client.get(
            f"/api/v1/port-forwards/{forward.id}",
            headers=_auth_headers(user.id),
        )
        assert resp.status_code == 200
        assert resp.json()["subdomain"] == "myapp"

    async def test_cannot_get_other_users_forward(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user1 = await _create_user(db_session, "owner")
        user2 = await _create_user(db_session, "other")
        forward = await _create_forward(db_session, user1.id)

        resp = await client.get(
            f"/api/v1/port-forwards/{forward.id}",
            headers=_auth_headers(user2.id),
        )
        assert resp.status_code == 404

    async def test_nonexistent_forward(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        fake_id = uuid.uuid4()

        resp = await client.get(
            f"/api/v1/port-forwards/{fake_id}",
            headers=_auth_headers(user.id),
        )
        assert resp.status_code == 404


# ── Delete Forward ──


class TestDeleteForward:
    async def test_delete_own_forward(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        forward = await _create_forward(db_session, user.id)

        resp = await client.delete(
            f"/api/v1/port-forwards/{forward.id}",
            headers=_auth_headers(user.id),
        )
        assert resp.status_code == 204

        # Verify it was deleted from the DB
        result = await db_session.execute(
            select(PortForward).where(PortForward.id == forward.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_cannot_delete_other_users_forward(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user1 = await _create_user(db_session, "owner")
        user2 = await _create_user(db_session, "attacker")
        forward = await _create_forward(db_session, user1.id)

        resp = await client.delete(
            f"/api/v1/port-forwards/{forward.id}",
            headers=_auth_headers(user2.id),
        )
        assert resp.status_code == 404

        # Original forward still exists in the DB
        result = await db_session.execute(
            select(PortForward).where(PortForward.id == forward.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_delete_nonexistent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        fake_id = uuid.uuid4()

        resp = await client.delete(
            f"/api/v1/port-forwards/{fake_id}",
            headers=_auth_headers(user.id),
        )
        assert resp.status_code == 404
