from fastapi import APIRouter

from aiso_core.api.v1 import auth, beta, container, file_system, health

api_router = APIRouter()

api_router.include_router(health.router, prefix="/v1", tags=["health"])
api_router.include_router(beta.router, prefix="/v1/beta", tags=["beta"])
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(container.router, prefix="/v1/container", tags=["container"])
api_router.include_router(file_system.router, prefix="/v1/fs", tags=["file-system"])
