from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.database import get_db
from aiso_core.dependencies import get_current_user
from aiso_core.models.user import User
from aiso_core.schemas.session import SaveSessionRequest, SessionResponse
from aiso_core.services.session_service import SessionService

router = APIRouter()


@router.get("", response_model=SessionResponse)
async def get_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse | Response:
    service = SessionService(db)
    result = await service.get_session(current_user.id)
    if result is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return result


@router.put("", response_model=SessionResponse)
async def save_session(
    data: SaveSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    service = SessionService(db)
    return await service.save_session(
        user_id=current_user.id,
        processes=data.processes,
        windows=data.windows,
        window_props=data.window_props,
        next_z_index=data.next_z_index,
        extra=data.extra,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = SessionService(db)
    await service.delete_session(current_user.id)
