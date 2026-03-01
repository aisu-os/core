"""Singleton Docker client.

Modul darajasida bitta ``DockerClient`` yaratiladi va butun jarayon davomida
qayta ishlatiladi.  Bu har chaqiriqda yangi client yaratish (va hech qachon
yopmaslik) natijasida kelib chiqadigan *file-descriptor leak* muammosini
to'liq bartaraf etadi.

Ishlatish::

    from aiso_core.services.docker_client import get_docker_client

    client = get_docker_client()
"""

from __future__ import annotations

import atexit
import logging
import threading

import docker

from aiso_core.config import settings

logger = logging.getLogger(__name__)

_client: docker.DockerClient | None = None
_lock = threading.Lock()


def get_docker_client() -> docker.DockerClient:
    """Thread-safe singleton Docker client."""
    global _client  # noqa: PLW0603
    if _client is None:
        with _lock:
            if _client is None:
                _client = docker.DockerClient(base_url=settings.docker_base_url)
                logger.debug("Docker client created: %s", settings.docker_base_url)
    return _client


def _close_client() -> None:
    global _client  # noqa: PLW0603
    if _client is not None:
        try:
            _client.close()
            logger.debug("Docker client closed")
        except Exception:
            logger.debug("Error closing Docker client", exc_info=True)
        _client = None


atexit.register(_close_client)
