from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.models.container_event import ContainerEvent
from aiso_core.models.user_container import UserContainer

logger = logging.getLogger(__name__)


def _parse_mem_str(mem_str: str) -> int:
    """Memory stringni baytlarga o'giradi (masalan '1g' -> 1073741824)."""
    mem_str = mem_str.strip().lower()
    multipliers = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    if mem_str[-1] in multipliers:
        return int(mem_str[:-1]) * multipliers[mem_str[-1]]
    return int(mem_str)


def _get_docker_client():  # noqa: ANN202
    """Docker client yaratadi."""
    import docker

    return docker.DockerClient(base_url=settings.docker_base_url)


def _get_user_data_path(user_id: uuid.UUID) -> str:
    """Foydalanuvchi data yo'lini absolut qilib qaytaradi."""
    return os.path.abspath(os.path.join(settings.user_data_base_path, str(user_id)))


def _create_user_dirs(user_id: uuid.UUID) -> str:
    """Foydalanuvchi direktoriyalarini yaratadi."""
    base = _get_user_data_path(user_id)
    subdirs = ["documents", "projects", "downloads", "pictures", ".aisu", ".trash"]
    for subdir in subdirs:
        os.makedirs(os.path.join(base, subdir), exist_ok=True)
    return base


def _create_container_sync(
    user_id: uuid.UUID,
    cpu: int,
    disk_mb: int,
    ram_bytes: int,
) -> dict[str, Any]:
    """Sinxron Docker container yaratish + start.

    Args:
        user_id: Foydalanuvchi ID
        cpu: CPU yadro soni (User.cpu dan)
        disk_mb: Disk hajmi MB da (User.disk dan)
        ram_bytes: RAM hajmi baytlarda
    """
    try:
        client = _get_docker_client()
        container_name = f"aisu_{user_id}"
        user_data_path = _get_user_data_path(user_id)

        # CPU: Docker cpu_quota = cpu_count * cpu_period
        cpu_quota = cpu * settings.container_cpu_period

        run_kwargs: dict[str, Any] = {
            "image": settings.container_image,
            "name": container_name,
            "detach": True,
            "hostname": f"aisu-{str(user_id)[:8]}",
            "network": settings.container_network,
            "volumes": {
                user_data_path: {"bind": "/home/aisu/data", "mode": "rw"},
            },
            "cpu_quota": cpu_quota,
            "cpu_period": settings.container_cpu_period,
            "mem_limit": ram_bytes,
            "pids_limit": settings.container_pids_limit,
            "environment": {
                "AISU_USER_ID": str(user_id),
            },
            "labels": {
                "aisu.user_id": str(user_id),
                "aisu.managed": "true",
            },
        }
        if settings.container_runtime:
            run_kwargs["runtime"] = settings.container_runtime

        container = client.containers.run(**run_kwargs)

        container.reload()
        container_ip = None
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        if settings.container_network in networks:
            container_ip = networks[settings.container_network].get("IPAddress")

        return {
            "container_id": container.id,
            "container_name": container_name,
            "container_ip": container_ip,
            "status": "running",
        }
    except Exception:
        logger.exception("Container yaratishda xatolik: user_id=%s", user_id)
        return {
            "container_id": None,
            "container_name": f"aisu_{user_id}",
            "container_ip": None,
            "status": "error",
        }


class ContainerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _log_event(
        self,
        user_id: uuid.UUID,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """container_events ga yozish."""
        event = ContainerEvent(
            user_id=user_id,
            event_type=event_type,
            details=details,
        )
        self.db.add(event)
        await self.db.flush()

    async def provision_container(
        self,
        user_id: uuid.UUID,
        cpu: int,
        disk_mb: int,
    ) -> UserContainer:
        """To'liq provisioning: dirlar yaratish -> DB ga 'creating' yozish -> Docker ->
        DB yangilash.

        Args:
            user_id: Foydalanuvchi ID
            cpu: CPU yadro soni (User.cpu dan)
            disk_mb: Disk hajmi MB da (User.disk dan)
        """
        # RAM = cpu * ram_per_cpu
        ram_per_cpu = _parse_mem_str(settings.container_ram_per_cpu)
        ram_bytes = cpu * ram_per_cpu
        disk_bytes = disk_mb * 1024 * 1024  # MB -> bytes

        # User direktoriyalarini yaratish
        await asyncio.to_thread(_create_user_dirs, user_id)

        # DB ga "creating" holatda yozish
        container_record = UserContainer(
            user_id=user_id,
            container_name=f"aisu_{user_id}",
            status="creating",
            cpu_limit=cpu,
            ram_limit=ram_bytes,
            disk_limit=disk_bytes,
            network_rate=settings.container_network_rate,
        )
        self.db.add(container_record)
        await self.db.flush()
        await self.db.refresh(container_record)

        await self._log_event(user_id, "creating", {"cpu": cpu, "disk_mb": disk_mb})

        # Docker container yaratish (background thread)
        result = await asyncio.to_thread(_create_container_sync, user_id, cpu, disk_mb, ram_bytes)

        # DB yangilash
        container_record.container_id = result["container_id"]
        container_record.container_name = result["container_name"]
        container_record.container_ip = result["container_ip"]
        container_record.status = result["status"]
        if result["status"] == "running":
            container_record.started_at = datetime.now(UTC)

        await self.db.flush()

        # Event yozish
        event_type = "created" if result["status"] == "running" else "error"
        await self._log_event(user_id, event_type, result)

        return container_record

    async def get_container(self, user_id: uuid.UUID) -> UserContainer | None:
        """DB dan UserContainer olish."""
        stmt = select(UserContainer).where(UserContainer.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def start_container(self, user_id: uuid.UUID, cpu: int, disk_mb: int) -> dict[str, str]:
        """To'xtatilgan containerni ishga tushirish."""
        container_record = await self.get_container(user_id)
        if container_record is None:
            container_record = await self.provision_container(user_id, cpu, disk_mb)
            return {"status": container_record.status, "message": "Container provisioned"}

        if container_record.status == "running":
            return {"status": "running", "message": "Container already running"}

        try:
            client = _get_docker_client()
            try:
                docker_container = client.containers.get(container_record.container_name)
                docker_container.start()
                docker_container.reload()

                container_record.status = "running"
                container_record.started_at = datetime.now(UTC)

                networks = docker_container.attrs.get("NetworkSettings", {}).get("Networks", {})
                if settings.container_network in networks:
                    container_record.container_ip = networks[settings.container_network].get(
                        "IPAddress"
                    )

                await self.db.flush()
                await self._log_event(user_id, "started")
                return {"status": "running", "message": "Container started"}
            except Exception:
                logger.warning(
                    "Container not found in Docker, re-provisioning: user_id=%s", user_id
                )
                container_record = await self.provision_container(user_id, cpu, disk_mb)
                return {"status": container_record.status, "message": "Container re-provisioned"}
        except Exception:
            logger.exception("Container start xatolik: user_id=%s", user_id)
            return {"status": "error", "message": "Failed to start container"}

    async def stop_container(self, user_id: uuid.UUID) -> dict[str, str]:
        """Containerni to'xtatish."""
        container_record = await self.get_container(user_id)
        if container_record is None:
            return {"status": "error", "message": "Container not found"}

        if container_record.status == "stopped":
            return {"status": "stopped", "message": "Container already stopped"}

        try:
            client = _get_docker_client()
            docker_container = client.containers.get(container_record.container_name)
            docker_container.stop(timeout=10)

            container_record.status = "stopped"
            await self.db.flush()
            await self._log_event(user_id, "stopped")
            return {"status": "stopped", "message": "Container stopped"}
        except Exception:
            logger.exception("Container stop xatolik: user_id=%s", user_id)
            container_record.status = "error"
            await self.db.flush()
            return {"status": "error", "message": "Failed to stop container"}

    async def get_container_status_live(self, user_id: uuid.UUID) -> dict[str, str] | None:
        """Docker dan real-time status olish."""
        container_record = await self.get_container(user_id)
        if container_record is None:
            return None

        if not container_record.container_id:
            return {"status": container_record.status, "docker_status": "unknown"}

        try:
            client = _get_docker_client()
            docker_container = client.containers.get(container_record.container_id)
            docker_container.reload()
            docker_status = docker_container.status

            if docker_status != container_record.status:
                container_record.status = docker_status
                await self.db.flush()

            return {"status": container_record.status, "docker_status": docker_status}
        except Exception:
            logger.exception("Live status olishda xatolik: user_id=%s", user_id)
            return {"status": container_record.status, "docker_status": "unreachable"}
