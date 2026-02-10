from fastapi import APIRouter, Depends, HTTPException, status

from aiso_core.dependencies import get_current_user
from aiso_core.models.user import User
from aiso_core.schemas.app_install import InstallRequest, InstallResponse
from aiso_core.schemas.app_permission import PermissionStatusResponse, PermissionUpdate
from aiso_core.schemas.app_review import ReviewCreate, ReviewResponse

router = APIRouter()


@router.post("/apps/{app_id}/install", response_model=InstallResponse)
async def install_app(
    app_id: str,
    data: InstallRequest,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.delete("/apps/{app_id}/install", status_code=204)
async def uninstall_app(
    app_id: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.get("/installed")
async def get_installed_apps(current_user: User = Depends(get_current_user)):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.post("/apps/{app_id}/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    app_id: str,
    data: ReviewCreate,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.put("/apps/{app_id}/permissions", response_model=PermissionStatusResponse)
async def update_permissions(
    app_id: str,
    data: PermissionUpdate,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@router.get("/apps/{app_id}/permissions", response_model=PermissionStatusResponse)
async def get_permissions(
    app_id: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")
