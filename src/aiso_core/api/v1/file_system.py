from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.get("/tree", response_model=FileNodeTreeResponse)
async def get_tree(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.get_tree(current_user.id)


@router.get("/node", response_model=FileNodeResponse)
async def get_node(
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.get_node(current_user.id, path)


@router.get("/ls", response_model=DirectoryListingResponse)
async def list_directory(
    path: str = Query(...),
    sort_by: str = Query("name"),
    sort_dir: str = Query("asc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.list_directory(current_user.id, path, sort_by, sort_dir)


@router.post("/node", response_model=FileNodeResponse, status_code=201)
async def create_node(
    data: CreateNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.create_node(current_user.id, data)


@router.patch("/rename", response_model=MoveResultResponse)
async def rename_node(
    data: RenameNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.rename_node(current_user.id, data)


@router.post("/move", response_model=MoveResultResponse)
async def move_node(
    data: MoveNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.move_node(current_user.id, data)


@router.post("/copy", response_model=CopyResultResponse)
async def copy_node(
    data: CopyNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.copy_node(current_user.id, data)


@router.post("/delete", response_model=FileNodeResponse)
async def delete_node(
    data: DeleteNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.delete_node(current_user.id, data)


@router.post("/bulk-delete", response_model=BulkResultResponse)
async def bulk_delete(
    data: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.bulk_delete(current_user.id, data)


@router.post("/bulk-move", response_model=BulkResultResponse)
async def bulk_move(
    data: BulkMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.bulk_move(current_user.id, data)


@router.get("/trash", response_model=list[FileNodeResponse])
async def list_trash(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.list_trash(current_user.id)


@router.post("/restore", response_model=MoveResultResponse)
async def restore_node(
    data: RestoreNodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.restore_node(current_user.id, data)


@router.post("/empty-trash")
async def empty_trash(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    count = await service.empty_trash(current_user.id)
    return {"deleted": count}


@router.patch("/desktop-positions", response_model=list[FileNodeResponse])
async def update_desktop_positions(
    data: BatchUpdateDesktopPositionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.update_desktop_positions(current_user.id, data)


@router.get("/search", response_model=list[FileNodeResponse])
async def search_files(
    q: str = Query(..., min_length=1),
    path: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileSystemService(db)
    return await service.search(current_user.id, q, path)
