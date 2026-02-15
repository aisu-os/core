import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.config import settings
from aiso_core.database import get_db
from aiso_core.dependencies import get_current_user
from aiso_core.models.user import User
from aiso_core.schemas.file_system import (
    BatchUpdateDesktopPositionsRequest,
    BulkDeleteRequest,
    BulkMoveRequest,
    BulkResultResponse,
    CopyNodeRequest,
    CopyResultResponse,
    CreateNodeRequest,
    DeleteNodeRequest,
    DirectoryListingResponse,
    FileNodeResponse,
    FileNodeTreeResponse,
    MoveNodeRequest,
    MoveResultResponse,
    RenameNodeRequest,
    RestoreNodeRequest,
)
from aiso_core.services.file_system_service import FileSystemService

router = APIRouter()


async def _ensure_container_running(user: User) -> str:
    """Container ishayotganini tekshirish. container_name qaytaradi."""
    container_name = f"aisu_{user.id}"

    if not settings.container_enabled:
        return container_name

    try:
        from aiso_core.services.container_service import _get_docker_client

        client = _get_docker_client()
        container = await asyncio.to_thread(client.containers.get, container_name)
        if container.status != "running":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Container ishlamayapti. Avval terminal orqali tizimni ishga tushiring.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Container topilmadi. Avval terminal orqali tizimni ishga tushiring.",
        ) from exc

    return container_name


def _get_service(db: AsyncSession, container_name: str) -> FileSystemService:
    return FileSystemService(db, container_name)


@router.get("/tree", response_model=FileNodeTreeResponse)
async def get_tree(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.get_tree(current_user.id)


@router.get("/node", response_model=FileNodeResponse)
async def get_node(
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.get_node(current_user.id, path)


@router.get("/ls", response_model=DirectoryListingResponse)
async def list_directory(
    path: str = Query(...),
    sort_by: str = Query("name"),
    sort_dir: str = Query("asc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.list_directory(current_user.id, path, sort_by, sort_dir)


@router.post("/node", response_model=FileNodeResponse, status_code=201)
async def create_node(
    data: CreateNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.create_node(current_user.id, data)


@router.patch("/rename", response_model=MoveResultResponse)
async def rename_node(
    data: RenameNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.rename_node(current_user.id, data)


@router.post("/move", response_model=MoveResultResponse)
async def move_node(
    data: MoveNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.move_node(current_user.id, data)


@router.post("/copy", response_model=CopyResultResponse)
async def copy_node(
    data: CopyNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.copy_node(current_user.id, data)


@router.post("/delete", response_model=FileNodeResponse)
async def delete_node(
    data: DeleteNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.delete_node(current_user.id, data)


@router.post("/bulk-delete", response_model=BulkResultResponse)
async def bulk_delete(
    data: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.bulk_delete(current_user.id, data)


@router.post("/bulk-move", response_model=BulkResultResponse)
async def bulk_move(
    data: BulkMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.bulk_move(current_user.id, data)


@router.get("/trash", response_model=list[FileNodeResponse])
async def list_trash(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.list_trash(current_user.id)


@router.post("/restore", response_model=MoveResultResponse)
async def restore_node(
    data: RestoreNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.restore_node(current_user.id, data)


@router.post("/empty-trash")
async def empty_trash(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    count = await service.empty_trash(current_user.id)
    return {"deleted": count}


@router.patch("/desktop-positions", response_model=list[FileNodeResponse])
async def update_desktop_positions(
    data: BatchUpdateDesktopPositionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.update_desktop_positions(current_user.id, data)


@router.get("/search", response_model=list[FileNodeResponse])
async def search_files(
    q: str = Query(..., min_length=1),
    path: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    container_name = await _ensure_container_running(current_user)
    service = _get_service(db, container_name)
    return await service.search(current_user.id, q, path)
