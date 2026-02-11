from fastapi import APIRouter

from aiso_core.api.v1 import admin, auth, container, developer, file_system, health, market, user_apps

api_router = APIRouter()

api_router.include_router(health.router, prefix="/v1", tags=["health"])
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(market.router, prefix="/v1/market", tags=["market"])
api_router.include_router(user_apps.router, prefix="/v1/user", tags=["user-apps"])
api_router.include_router(developer.router, prefix="/v1/developer", tags=["developer"])
api_router.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
api_router.include_router(container.router, prefix="/v1/container", tags=["container"])
api_router.include_router(file_system.router, prefix="/v1/fs", tags=["file-system"])
