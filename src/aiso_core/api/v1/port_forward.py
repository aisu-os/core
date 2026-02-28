import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.database import get_db
from aiso_core.dependencies import get_current_user, rate_limit
from aiso_core.models.user import User
from aiso_core.schemas.port_forward import (
    CreatePortForwardRequest,
    PortForwardListResponse,
    PortForwardResponse,
)
from aiso_core.services.port_forward_service import PortForwardService

router = APIRouter()


@router.get("/config")
async def get_port_forward_config():
    """Port forward domain konfiguratsiyasi (frontend uchun)."""
    return {
        "domain": settings.port_forward_domain,
        "scheme": settings.port_forward_scheme,
    }


@router.get("", response_model=PortForwardListResponse)
async def list_forwards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PortForwardService(db)
    return await service.list_forwards(current_user.id)


@router.post("", response_model=PortForwardResponse, status_code=201)
async def create_forward(
    data: CreatePortForwardRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit(10, 60)),
):
    service = PortForwardService(db)
    return await service.create_forward(
        user_id=current_user.id,
        container_port=data.container_port,
        subdomain=data.subdomain,
    )


@router.get("/{forward_id}", response_model=PortForwardResponse)
async def get_forward(
    forward_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PortForwardService(db)
    return await service.get_forward(current_user.id, forward_id)


@router.delete("/{forward_id}", status_code=204)
async def delete_forward(
    forward_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PortForwardService(db)
    await service.delete_forward(current_user.id, forward_id)
