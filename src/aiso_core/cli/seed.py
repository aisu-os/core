"""Seed system apps into the database.

Usage:
    cd aiso-core
    uv run python -m aiso_core.cli.seed
"""

import asyncio
import logging
import sys

from aiso_core.database import async_session_factory
from aiso_core.services.system_app_service import SystemAppService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    async with async_session_factory() as session:
        service = SystemAppService(session)
        created = await service.seed_system_apps()
        await session.commit()

    logger.info("Seed complete. Created %d new system app(s).", created)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
