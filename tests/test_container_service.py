"""ContainerService unit testlari.

Docker haqiqiy bo'lmagan muhitda mock bilan ishlaydi.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.models.user import User
from aiso_core.models.user_container import UserContainer
from aiso_core.services.container_service import (
    ContainerService,
    _create_container_sync,
    _create_user_dirs,
    _get_user_data_path,
    _parse_mem_str,
)

# ── Yordamchi funksiyalar testlari ──


class TestParseMemStr:

    def test_gigabytes(self) -> None:
        assert _parse_mem_str("1g") == 1024**3

    def test_megabytes(self) -> None:
        assert _parse_mem_str("512m") == 512 * 1024**2

    def test_kilobytes(self) -> None:
        assert _parse_mem_str("100k") == 100 * 1024

    def test_terabytes(self) -> None:
        assert _parse_mem_str("1t") == 1024**4

    def test_plain_bytes(self) -> None:
        assert _parse_mem_str("1024") == 1024

    def test_uppercase(self) -> None:
        assert _parse_mem_str("2G") == 2 * 1024**3

    def test_with_spaces(self) -> None:
        assert _parse_mem_str("  4m  ") == 4 * 1024**2


class TestGetUserDataPath:

    def test_returns_absolute_path(self) -> None:
        uid = uuid.uuid4()
        path = _get_user_data_path(uid)
        assert str(uid) in path
        assert path.startswith("/")

    def test_path_contains_user_id(self) -> None:
        uid = uuid.uuid4()
        path = _get_user_data_path(uid)
        assert str(uid) in path


class TestCreateUserDirs:

    def test_creates_all_subdirs(self, tmp_path) -> None:
        uid = uuid.uuid4()
        with patch.object(settings, "user_data_base_path", str(tmp_path)):
            base = _create_user_dirs(uid)

        expected_dirs = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", ".Trash"]
        for d in expected_dirs:
            assert (tmp_path / str(uid) / d).is_dir()
        assert str(uid) in base

    def test_idempotent(self, tmp_path) -> None:
        uid = uuid.uuid4()
        with patch.object(settings, "user_data_base_path", str(tmp_path)):
            _create_user_dirs(uid)
            _create_user_dirs(uid)  # ikkinchi marta xatolik bermaydi


class TestCreateContainerSync:

    def test_success_returns_running(self) -> None:
        mock_container = MagicMock()
        mock_container.id = "abc123"
        mock_container.attrs = {
            "NetworkSettings": {
                "Networks": {
                    settings.container_network: {"IPAddress": "172.18.0.5"}
                }
            }
        }

        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container

        uid = uuid.uuid4()
        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ), patch(
            "aiso_core.services.container_service._get_user_data_path",
            return_value="/data/users/" + str(uid),
        ):
            result = _create_container_sync(uid, cpu=2, disk_mb=5120, ram_bytes=2 * 1024**3)

        assert result["status"] == "running"
        assert result["container_id"] == "abc123"
        assert result["container_ip"] == "172.18.0.5"
        assert result["container_name"] == f"aisu_{uid}"

    def test_docker_error_returns_error(self) -> None:
        mock_client = MagicMock()
        mock_client.containers.run.side_effect = RuntimeError("Docker daemon not found")

        uid = uuid.uuid4()
        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ), patch(
            "aiso_core.services.container_service._get_user_data_path",
            return_value="/data/users/" + str(uid),
        ):
            result = _create_container_sync(uid, cpu=2, disk_mb=5120, ram_bytes=2 * 1024**3)

        assert result["status"] == "error"
        assert result["container_id"] is None
        assert result["container_ip"] is None

    def test_no_network_ip(self) -> None:
        mock_container = MagicMock()
        mock_container.id = "abc123"
        mock_container.attrs = {"NetworkSettings": {"Networks": {}}}

        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container

        uid = uuid.uuid4()
        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ), patch(
            "aiso_core.services.container_service._get_user_data_path",
            return_value="/data/users/" + str(uid),
        ):
            result = _create_container_sync(uid, cpu=2, disk_mb=5120, ram_bytes=2 * 1024**3)

        assert result["status"] == "running"
        assert result["container_ip"] is None


# ── ContainerService testlari ──


class TestContainerService:

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        user = User(
            id=uuid.uuid4(),
            email="container_test@test.com",
            username="container_test",
            display_name="Container Test",
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

    async def test_get_container_returns_none_when_not_exists(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        service = ContainerService(db_session)
        result = await service.get_container(user.id)
        assert result is None

    async def test_provision_container_creates_record(
        self, db_session: AsyncSession, user: User, tmp_path,
    ) -> None:
        mock_result = {
            "container_id": "docker_abc",
            "container_name": f"aisu_{user.id}",
            "container_ip": "172.18.0.5",
            "status": "running",
        }

        with patch.object(settings, "user_data_base_path", str(tmp_path)), \
             patch(
                 "aiso_core.services.container_service._create_container_sync",
                 return_value=mock_result,
             ):
            service = ContainerService(db_session)
            record = await service.provision_container(user.id, cpu=2, disk_mb=5120)
            await db_session.commit()

        assert record.status == "running"
        assert record.container_id == "docker_abc"
        assert record.container_ip == "172.18.0.5"
        assert record.user_id == user.id
        assert record.started_at is not None

    async def test_provision_container_error_status(
        self, db_session: AsyncSession, user: User, tmp_path,
    ) -> None:
        mock_result = {
            "container_id": None,
            "container_name": f"aisu_{user.id}",
            "container_ip": None,
            "status": "error",
        }

        with patch.object(settings, "user_data_base_path", str(tmp_path)), \
             patch(
                 "aiso_core.services.container_service._create_container_sync",
                 return_value=mock_result,
             ):
            service = ContainerService(db_session)
            record = await service.provision_container(user.id, cpu=2, disk_mb=5120)
            await db_session.commit()

        assert record.status == "error"
        assert record.container_id is None
        assert record.started_at is None

    async def test_get_container_returns_existing(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        service = ContainerService(db_session)
        result = await service.get_container(user.id)
        assert result is not None
        assert result.container_id == "docker_123"

    async def test_start_container_provisions_when_no_record(
        self, db_session: AsyncSession, user: User, tmp_path,
    ) -> None:
        mock_result = {
            "container_id": "docker_new",
            "container_name": f"aisu_{user.id}",
            "container_ip": "172.18.0.10",
            "status": "running",
        }

        with patch.object(settings, "user_data_base_path", str(tmp_path)), \
             patch(
                 "aiso_core.services.container_service._create_container_sync",
                 return_value=mock_result,
             ):
            service = ContainerService(db_session)
            result = await service.start_container(user.id, cpu=2, disk_mb=5120)
            await db_session.commit()

        assert result["status"] == "running"
        assert result["message"] == "Container provisioned"

    async def test_start_container_already_running(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_docker_container.status = "running"
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.start_container(user.id, cpu=2, disk_mb=5120)

        assert result["status"] == "running"
        assert result["message"] == "Container already running"

    async def test_start_container_stopped_starts_it(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="stopped",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_docker_container.status = "exited"
        mock_docker_container.attrs = {
            "NetworkSettings": {
                "Networks": {
                    settings.container_network: {"IPAddress": "172.18.0.6"}
                }
            }
        }
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.start_container(user.id, cpu=2, disk_mb=5120)
            await db_session.commit()

        assert result["status"] == "running"
        assert result["message"] == "Container started"
        mock_docker_container.start.assert_called_once()

    async def test_start_container_docker_not_found_reprovisions(
        self, db_session: AsyncSession, user: User, tmp_path,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_old",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = Exception("Not found")

        mock_result = {
            "container_id": "docker_new",
            "container_name": f"aisu_{user.id}",
            "container_ip": "172.18.0.11",
            "status": "running",
        }

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ), patch.object(settings, "user_data_base_path", str(tmp_path)), \
             patch(
                 "aiso_core.services.container_service._create_container_sync",
                 return_value=mock_result,
             ):
            service = ContainerService(db_session)
            result = await service.start_container(user.id, cpu=2, disk_mb=5120)
            await db_session.commit()

        assert result["status"] == "running"
        assert result["message"] == "Container re-provisioned"

    async def test_stop_container_no_record(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        service = ContainerService(db_session)
        result = await service.stop_container(user.id)
        assert result["status"] == "error"
        assert result["message"] == "Container not found"

    async def test_stop_container_already_stopped(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="stopped",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        service = ContainerService(db_session)
        result = await service.stop_container(user.id)
        assert result["status"] == "stopped"
        assert result["message"] == "Container already stopped"

    async def test_stop_container_success(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.stop_container(user.id)
            await db_session.commit()

        assert result["status"] == "stopped"
        assert result["message"] == "Container stopped"
        mock_docker_container.stop.assert_called_once_with(timeout=10)

    async def test_stop_container_docker_error(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = Exception("Docker error")

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.stop_container(user.id)
            await db_session.commit()

        assert result["status"] == "error"

    async def test_get_container_status_live_no_record(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        service = ContainerService(db_session)
        result = await service.get_container_status_live(user.id)
        assert result is None

    async def test_get_container_status_live_no_container_id(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id=None,
            status="creating",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        service = ContainerService(db_session)
        result = await service.get_container_status_live(user.id)
        assert result is not None
        assert result["status"] == "creating"
        assert result["docker_status"] == "unknown"

    async def test_get_container_status_live_success(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_docker_container.status = "running"
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.get_container_status_live(user.id)

        assert result is not None
        assert result["status"] == "running"
        assert result["docker_status"] == "running"

    async def test_get_container_status_live_docker_unreachable(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = Exception("Connection refused")

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.get_container_status_live(user.id)

        assert result is not None
        assert result["docker_status"] == "unreachable"

    async def test_get_container_status_live_syncs_status(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        """Docker da status o'zgargan bo'lsa, DB ni yangilaydi."""
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="running",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_docker_container.status = "exited"  # Docker da boshqa status
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.get_container_status_live(user.id)
            await db_session.commit()

        assert result["status"] == "exited"
        assert result["docker_status"] == "exited"

    async def test_start_container_syncs_running_status(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        """DB da stopped, Docker da running — DB sinxronlanishi kerak."""
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="stopped",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_docker_container.status = "running"
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.start_container(user.id, cpu=2, disk_mb=5120)
            await db_session.commit()

        assert result["status"] == "running"
        assert result["message"] == "Container already running"

    async def test_start_container_start_fails(
        self, db_session: AsyncSession, user: User,
    ) -> None:
        """Docker da container bor lekin start qilishda xatolik."""
        container = UserContainer(
            user_id=user.id,
            container_name=f"aisu_{user.id}",
            container_id="docker_123",
            status="stopped",
            cpu_limit=2,
            ram_limit=2 * 1024**3,
            disk_limit=5120 * 1024 * 1024,
            network_rate="5mbit",
        )
        db_session.add(container)
        await db_session.commit()

        mock_docker_container = MagicMock()
        mock_docker_container.status = "exited"
        mock_docker_container.start.side_effect = Exception("Start failed")
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_docker_container

        with patch(
            "aiso_core.services.container_service._get_docker_client",
            return_value=mock_client,
        ):
            service = ContainerService(db_session)
            result = await service.start_container(user.id, cpu=2, disk_mb=5120)

        assert result["status"] == "error"
        assert result["message"] == "Failed to start container"
