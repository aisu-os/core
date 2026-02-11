from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import get_db
from aiso_core.dependencies import get_current_user
from aiso_core.models.user import User
from aiso_core.schemas.container import ContainerActionResponse, ContainerStatusResponse
from aiso_core.services.container_service import ContainerService

router = APIRouter()


@router.get("/status", response_model=ContainerStatusResponse)
async def get_container_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ContainerService(db)
    container = await service.get_container(current_user.id)
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Container not found",
        )
    return ContainerStatusResponse.model_validate(container)


@router.post("/start", response_model=ContainerActionResponse)
async def start_container(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ContainerService(db)
    result = await service.start_container(
        current_user.id, cpu=current_user.cpu, disk_mb=current_user.disk
    )
    return ContainerActionResponse(**result)


@router.post("/stop", response_model=ContainerActionResponse)
async def stop_container(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ContainerService(db)
    result = await service.stop_container(current_user.id)
    return ContainerActionResponse(**result)


@router.post("/restart", response_model=ContainerActionResponse)
async def restart_container(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ContainerService(db)
    await service.stop_container(current_user.id)
    result = await service.start_container(
        current_user.id, cpu=current_user.cpu, disk_mb=current_user.disk
    )
    return ContainerActionResponse(**result)
