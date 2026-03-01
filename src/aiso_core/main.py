from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from aiso_core.api.router import api_router
from aiso_core.api.v1.terminal import router as terminal_ws_router
from aiso_core.config import settings

if settings.sentry_dsn and settings.environment == "production":
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.2,
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _sync_caddy_routes()
    yield
    from aiso_core.database import engine

    await engine.dispose()


async def _sync_caddy_routes() -> None:
    """Startup: load all active port forwards into Caddy."""
    import logging

    from sqlalchemy import select

    from aiso_core.database import async_session_factory
    from aiso_core.models.port_forward import PortForward
    from aiso_core.services.caddy_service import CaddyService

    logger = logging.getLogger(__name__)
    if not settings.container_enabled:
        logger.info("Sync: skipped because containers are disabled")
        return

    caddy = CaddyService()
    if not caddy.enabled:
        return

    async with async_session_factory() as session:
        stmt = select(PortForward).where(PortForward.status == "active")
        result = await session.execute(stmt)
        forwards = list(result.scalars().all())

    if not forwards:
        logger.info("Sync: no active port forwards")
        return

    route_data = [
        {
            "subdomain": f.subdomain,
            "upstream": f"{f.container_ip}:{f.container_port}",
        }
        for f in forwards
        if f.container_ip
    ]
    await caddy.sync_routes(route_data)


def create_app() -> FastAPI:
    is_prod = settings.environment == "production"
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")

    app.include_router(api_router, prefix="/api")
    app.include_router(terminal_ws_router, prefix="/ws")

    return app


app = create_app()
