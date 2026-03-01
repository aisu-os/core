from __future__ import annotations

import asyncio
import logging
import os
import shutil
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
    """Convert memory string to bytes (e.g. '1g' -> 1073741824)."""
    mem_str = mem_str.strip().lower()
    multipliers = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    if mem_str[-1] in multipliers:
        return int(mem_str[:-1]) * multipliers[mem_str[-1]]
    return int(mem_str)


def _get_docker_client():  # noqa: ANN202
    """Create a Docker client."""
    import docker

    return docker.DockerClient(base_url=settings.docker_base_url)


def _get_user_data_path(user_id: uuid.UUID) -> str:
    """Return the absolute path for user data."""
    return os.path.abspath(os.path.join(settings.user_data_base_path, str(user_id)))


_DOTFILES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "docker", "user-base")
)


def _copy_default_dotfiles(home_dir: str) -> None:
    """Copy default dotfiles to the home directory (only if they don't exist)."""
    dotfiles = {
        "bashrc.default": ".bashrc",
        "profile.default": ".profile",
    }
    for src_name, dest_name in dotfiles.items():
        src = os.path.join(_DOTFILES_DIR, src_name)
        dest = os.path.join(home_dir, dest_name)
        if not os.path.exists(dest) and os.path.exists(src):
            shutil.copy2(src, dest)


def _create_user_dirs(user_id: uuid.UUID) -> str:
    """Create user directories."""
    base = _get_user_data_path(user_id)
    subdirs = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", ".Trash"]
    for subdir in subdirs:
        os.makedirs(os.path.join(base, subdir), exist_ok=True)

    # Copy default dotfiles (only if they don't exist)
    _copy_default_dotfiles(base)

    return base


def _create_container_sync(
    user_id: uuid.UUID,
    cpu: int,
    disk_mb: int,
    ram_bytes: int,
) -> dict[str, Any]:
    """Synchronous Docker container create + start.

    Args:
        user_id: User ID
        cpu: CPU core count (from User.cpu)
        disk_mb: Disk size in MB (from User.disk)
        ram_bytes: RAM size in bytes
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
            "stdin_open": True,
            "tty": True,
            "hostname": f"aisu-{str(user_id)[:8]}",
            "network": settings.container_network,
            "volumes": {
                user_data_path: {"bind": "/home/aisu", "mode": "rw"},
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
        logger.exception("Error creating container: user_id=%s", user_id)
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
        """Write to container_events."""
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
        """Full provisioning: create dirs -> write 'creating' to DB -> Docker ->
        update DB.

        Args:
            user_id: User ID
            cpu: CPU core count (from User.cpu)
            disk_mb: Disk size in MB (from User.disk)
        """
        # RAM = cpu * ram_per_cpu
        ram_per_cpu = _parse_mem_str(settings.container_ram_per_cpu)
        ram_bytes = cpu * ram_per_cpu
        disk_bytes = disk_mb * 1024 * 1024  # MB -> bytes

        # Create user directories
        await asyncio.to_thread(_create_user_dirs, user_id)

        # Write to DB in "creating" state
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

        # Create Docker container (background thread)
        result = await asyncio.to_thread(_create_container_sync, user_id, cpu, disk_mb, ram_bytes)

        # Update DB
        container_record.container_id = result["container_id"]
        container_record.container_name = result["container_name"]
        container_record.container_ip = result["container_ip"]
        container_record.status = result["status"]
        if result["status"] == "running":
            container_record.started_at = datetime.now(UTC)

        await self.db.flush()

        # Log event
        event_type = "created" if result["status"] == "running" else "error"
        await self._log_event(user_id, event_type, result)

        return container_record

    async def get_container(self, user_id: uuid.UUID) -> UserContainer | None:
        """Get UserContainer from DB."""
        stmt = select(UserContainer).where(UserContainer.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _reprovision_container(
        self,
        container_record: UserContainer,
        user_id: uuid.UUID,
        cpu: int,
        disk_mb: int,
    ) -> UserContainer:
        """Re-create the Docker container while preserving the existing DB record.

        Unlike provision_container(), this does not create a new UserContainer,
        it updates the existing record (prevents duplicate key errors).
        """
        ram_per_cpu = _parse_mem_str(settings.container_ram_per_cpu)
        ram_bytes = cpu * ram_per_cpu
        disk_bytes = disk_mb * 1024 * 1024

        await asyncio.to_thread(_create_user_dirs, user_id)

        container_record.status = "creating"
        container_record.cpu_limit = cpu
        container_record.ram_limit = ram_bytes
        container_record.disk_limit = disk_bytes
        container_record.network_rate = settings.container_network_rate
        await self.db.flush()

        await self._log_event(user_id, "re-creating", {"cpu": cpu, "disk_mb": disk_mb})

        result = await asyncio.to_thread(_create_container_sync, user_id, cpu, disk_mb, ram_bytes)

        container_record.container_id = result["container_id"]
        container_record.container_name = result["container_name"]
        container_record.container_ip = result["container_ip"]
        container_record.status = result["status"]
        if result["status"] == "running":
            container_record.started_at = datetime.now(UTC)

        await self.db.flush()

        event_type = "created" if result["status"] == "running" else "error"
        await self._log_event(user_id, event_type, result)

        return container_record

    async def start_container(self, user_id: uuid.UUID, cpu: int, disk_mb: int) -> dict[str, str]:
        """Start a container.

        - No DB record → new provision
        - Docker container exists and running → return immediately
        - Docker container exists but stopped → start it
        - Docker container missing (deleted) → re-provision (update DB record)
        """
        container_record = await self.get_container(user_id)
        if container_record is None:
            container_record = await self.provision_container(user_id, cpu, disk_mb)
            return {"status": container_record.status, "message": "Container provisioned"}

        # Check actual state in Docker
        try:
            docker_container = await asyncio.to_thread(
                _get_docker_client().containers.get,
                container_record.container_name,
            )
            docker_status = docker_container.status
        except Exception:
            docker_container = None
            docker_status = None

        # Container not in Docker — re-create
        if docker_container is None:
            logger.warning(
                "Container not found in Docker, re-provisioning: user_id=%s",
                user_id,
            )
            container_record = await self._reprovision_container(
                container_record,
                user_id,
                cpu,
                disk_mb,
            )
            return {"status": container_record.status, "message": "Container re-provisioned"}

        # Running in Docker — sync DB and return
        if docker_status == "running":
            if container_record.status != "running":
                container_record.status = "running"
                container_record.started_at = datetime.now(UTC)
                await self.db.flush()
            return {"status": "running", "message": "Container already running"}

        # Exists in Docker but stopped — start it
        try:
            await asyncio.to_thread(docker_container.start)
            await asyncio.to_thread(docker_container.reload)

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
            logger.exception("Container start error: user_id=%s", user_id)
            return {"status": "error", "message": "Failed to start container"}

    async def stop_container(self, user_id: uuid.UUID) -> dict[str, str]:
        """Stop a container."""
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
            logger.exception("Container stop error: user_id=%s", user_id)
            container_record.status = "error"
            await self.db.flush()
            return {"status": "error", "message": "Failed to stop container"}

    async def get_container_status_live(self, user_id: uuid.UUID) -> dict[str, str] | None:
        """Get real-time status from Docker."""
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
            logger.exception("Error getting live status: user_id=%s", user_id)
            return {"status": container_record.status, "docker_status": "unreachable"}
