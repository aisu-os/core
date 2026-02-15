"""Fayl tizimi servisi — Docker container file system bilan ishlaydi.

Barcha fayl operatsiyalari ContainerFsService orqali haqiqiy
Docker container ichidagi fayl tizimida bajariladi. Database faqat
desktop pozitsiyalar va trash metadata uchun ishlatiladi.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.file_system_node import FileSystemNode
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
    path_to_uuid,
)
from aiso_core.services.container_fs_service import ContainerFsService


def _ts_from_epoch(epoch: float) -> datetime:
    """Unix epoch (float) ni datetime ga o'giradi."""
    return datetime.fromtimestamp(epoch, tz=UTC)


def _build_node_response(
    raw: dict,
    user_id: uuid.UUID,
    vfs_path: str,
    base_path: str,
    *,
    is_trashed: bool = False,
    original_path: str | None = None,
    trashed_at: datetime | None = None,
    desktop_x: int | None = None,
    desktop_y: int | None = None,
) -> FileNodeResponse:
    """Container stat dict'dan FileNodeResponse yaratish."""
    return FileNodeResponse(
        id=path_to_uuid(user_id, vfs_path),
        name=raw.get("name", vfs_path.rsplit("/", 1)[-1] or "/"),
        path=vfs_path,
        node_type=raw.get("type", "file"),
        mime_type=raw.get("mime_type"),
        size=raw.get("size", 0),
        is_trashed=is_trashed,
        original_path=original_path,
        trashed_at=trashed_at,
        desktop_x=desktop_x,
        desktop_y=desktop_y,
        created_at=_ts_from_epoch(raw.get("ctime", 0)),
        updated_at=_ts_from_epoch(raw.get("mtime", 0)),
    )


def _build_tree_response(
    raw: dict,
    user_id: uuid.UUID,
    base_path: str,
    metadata_map: dict[str, FileSystemNode],
) -> FileNodeTreeResponse:
    """Container tree dict'dan rekursiv FileNodeTreeResponse yaratish."""
    # Container path → VFS path
    container_path = raw.get("path", base_path)
    if container_path == base_path or container_path == base_path + "/":
        vfs_path = "/"
    elif container_path.startswith(base_path + "/"):
        vfs_path = container_path[len(base_path) :]
    else:
        vfs_path = container_path

    meta = metadata_map.get(vfs_path)

    children: list[FileNodeTreeResponse] = []
    for child_raw in raw.get("children", []):
        children.append(_build_tree_response(child_raw, user_id, base_path, metadata_map))

    return FileNodeTreeResponse(
        id=path_to_uuid(user_id, vfs_path),
        name=raw.get("name", vfs_path.rsplit("/", 1)[-1] or "/"),
        path=vfs_path,
        node_type=raw.get("type", "file"),
        mime_type=raw.get("mime_type"),
        size=raw.get("size", 0),
        is_trashed=False,
        desktop_x=meta.desktop_x if meta else None,
        desktop_y=meta.desktop_y if meta else None,
        created_at=_ts_from_epoch(raw.get("ctime", 0)),
        updated_at=_ts_from_epoch(raw.get("mtime", 0)),
        children=children,
    )


class FileSystemService:
    def __init__(self, db: AsyncSession, container_name: str):
        self.db = db
        self.cfs = ContainerFsService(container_name)

    # ── Yordamchi: metadata olish ──

    async def _get_metadata_map(self, user_id: uuid.UUID) -> dict[str, FileSystemNode]:
        """DB'dan barcha metadata (desktop pozitsiyalar) ni olish."""
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.desktop_x.is_not(None),
            )
        )
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()
        return {n.path: n for n in nodes}

    async def _get_trash_metadata(self, user_id: uuid.UUID) -> dict[str, FileSystemNode]:
        """Trash metadata (original_path) ni olish."""
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.is_trashed == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()
        return {n.path: n for n in nodes}

    async def _upsert_metadata(
        self,
        user_id: uuid.UUID,
        path: str,
        *,
        desktop_x: int | None = None,
        desktop_y: int | None = None,
        is_trashed: bool = False,
        original_path: str | None = None,
    ) -> None:
        """DB'da metadata yaratish yoki yangilash."""
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == path,
            )
        )
        result = await self.db.execute(stmt)
        node = result.scalar_one_or_none()

        if node:
            if desktop_x is not None:
                node.desktop_x = desktop_x
            if desktop_y is not None:
                node.desktop_y = desktop_y
            node.is_trashed = is_trashed
            node.original_path = original_path
        else:
            node = FileSystemNode(
                user_id=user_id,
                parent_id=None,
                name=path.rsplit("/", 1)[-1] or "/",
                path=path,
                node_type="file",
                desktop_x=desktop_x,
                desktop_y=desktop_y,
                is_trashed=is_trashed,
                original_path=original_path,
            )
            self.db.add(node)

        await self.db.flush()

    async def _delete_metadata(self, user_id: uuid.UUID, path: str) -> None:
        """DB'dan metadata o'chirish."""
        await self.db.execute(
            delete(FileSystemNode).where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.path == path,
                )
            )
        )
        await self.db.flush()

    async def _update_metadata_path(self, user_id: uuid.UUID, old_path: str, new_path: str) -> None:
        """Metadata path ni yangilash (rename/move uchun)."""
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == old_path,
            )
        )
        result = await self.db.execute(stmt)
        node = result.scalar_one_or_none()
        if node:
            node.path = new_path
            node.name = new_path.rsplit("/", 1)[-1] or "/"
            await self.db.flush()

    # ── Public API ──

    async def get_tree(self, user_id: uuid.UUID) -> FileNodeTreeResponse:
        """Butun fayl tizimi daraxtini olish."""
        raw_tree = await self.cfs.get_tree()
        metadata_map = await self._get_metadata_map(user_id)
        return _build_tree_response(raw_tree, user_id, self.cfs.base_path, metadata_map)

    async def get_node(self, user_id: uuid.UUID, path: str) -> FileNodeResponse:
        """Bitta node haqida ma'lumot olish."""
        raw = await self.cfs.stat_path(path)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node not found: {path}",
            )
        return _build_node_response(raw, user_id, path, self.cfs.base_path)

    async def list_directory(
        self,
        user_id: uuid.UUID,
        path: str,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> DirectoryListingResponse:
        """Papka tarkibini ro'yxatlash."""
        # Parent node stat
        parent_raw = await self.cfs.stat_path(path)
        if parent_raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Directory not found: {path}",
            )
        if parent_raw.get("type") != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not a directory",
            )

        # Bolalar
        children_raw = await self.cfs.list_directory(path)
        metadata_map = await self._get_metadata_map(user_id)

        children: list[FileNodeResponse] = []
        for child in children_raw:
            child_container_path = child.get("path", "")
            if child_container_path.startswith(self.cfs.base_path + "/"):
                child_vfs = child_container_path[len(self.cfs.base_path) :]
            elif child_container_path.startswith(self.cfs.base_path):
                child_vfs = "/"
            else:
                child_vfs = child_container_path

            meta = metadata_map.get(child_vfs)
            children.append(
                _build_node_response(
                    child,
                    user_id,
                    child_vfs,
                    self.cfs.base_path,
                    desktop_x=meta.desktop_x if meta else None,
                    desktop_y=meta.desktop_y if meta else None,
                )
            )

        # Saralash
        sort_key_map = {
            "name": lambda n: n.name.lower(),
            "size": lambda n: n.size,
            "created_at": lambda n: n.created_at,
            "updated_at": lambda n: n.updated_at,
        }
        key_fn = sort_key_map.get(sort_by, sort_key_map["name"])
        children.sort(key=key_fn, reverse=(sort_dir == "desc"))

        parent_response = _build_node_response(parent_raw, user_id, path, self.cfs.base_path)

        return DirectoryListingResponse(
            path=path,
            node=parent_response,
            children=children,
            total=len(children),
        )

    async def create_node(self, user_id: uuid.UUID, data: CreateNodeRequest) -> FileNodeResponse:
        """Fayl yoki papka yaratish."""
        # Parent mavjudligini tekshirish
        parent_raw = await self.cfs.stat_path(data.parent_path)
        if parent_raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent not found: {data.parent_path}",
            )
        if parent_raw.get("type") != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent is not a directory",
            )

        # Unikal nom
        unique_name = await self.cfs.generate_unique_name(data.parent_path, data.name)
        new_vfs = (
            f"/{unique_name}" if data.parent_path == "/" else f"{data.parent_path}/{unique_name}"
        )

        # Container ichida yaratish
        if data.node_type == "directory":
            await self.cfs.create_directory(new_vfs)
        else:
            await self.cfs.create_file(new_vfs)

        # Stat olish
        raw = await self.cfs.stat_path(new_vfs)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Node created but stat failed",
            )

        return _build_node_response(raw, user_id, new_vfs, self.cfs.base_path)

    async def rename_node(self, user_id: uuid.UUID, data: RenameNodeRequest) -> MoveResultResponse:
        """Fayl/papkani qayta nomlash."""
        if data.path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rename root",
            )

        # Mavjudligini tekshirish
        if not await self.cfs.exists(data.path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node not found: {data.path}",
            )

        parent_path = data.path.rsplit("/", 1)[0] or "/"
        new_path = f"/{data.new_name}" if parent_path == "/" else f"{parent_path}/{data.new_name}"

        # Nom takrorlanishini tekshirish
        if await self.cfs.exists(new_path):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Name already exists: {data.new_name}",
            )

        # Container ichida rename
        await self.cfs.rename(data.path, new_path)

        # DB metadata yangilash
        await self._update_metadata_path(user_id, data.path, new_path)

        # Stat olish
        raw = await self.cfs.stat_path(new_path)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Renamed but stat failed",
            )

        return MoveResultResponse(
            old_path=data.path,
            new_path=new_path,
            node=_build_node_response(raw, user_id, new_path, self.cfs.base_path),
        )

    async def move_node(self, user_id: uuid.UUID, data: MoveNodeRequest) -> MoveResultResponse:
        """Faylni boshqa papkaga ko'chirish."""
        if data.source_path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move root",
            )

        # O'ziga ko'chirish mumkin emas
        if data.dest_parent_path == data.source_path or data.dest_parent_path.startswith(
            data.source_path + "/"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move into itself or its descendant",
            )

        # Mavjudlik tekshiruvi
        if not await self.cfs.exists(data.source_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source not found: {data.source_path}",
            )

        dest_raw = await self.cfs.stat_path(data.dest_parent_path)
        if dest_raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination not found: {data.dest_parent_path}",
            )
        if dest_raw.get("type") != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination is not a directory",
            )

        # Nom unikal qilish
        source_name = data.source_path.rsplit("/", 1)[-1]
        unique_name = await self.cfs.generate_unique_name(data.dest_parent_path, source_name)

        # Agar nom o'zgarsa, avval rename kerak
        if unique_name != source_name:
            parent_path = data.source_path.rsplit("/", 1)[0] or "/"
            temp_path = f"/{unique_name}" if parent_path == "/" else f"{parent_path}/{unique_name}"
            await self.cfs.rename(data.source_path, temp_path)
            new_vfs = await self.cfs.move(temp_path, data.dest_parent_path)
        else:
            new_vfs = await self.cfs.move(data.source_path, data.dest_parent_path)

        # DB metadata yangilash
        await self._update_metadata_path(user_id, data.source_path, new_vfs)

        raw = await self.cfs.stat_path(new_vfs)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Moved but stat failed",
            )

        return MoveResultResponse(
            old_path=data.source_path,
            new_path=new_vfs,
            node=_build_node_response(raw, user_id, new_vfs, self.cfs.base_path),
        )

    async def copy_node(self, user_id: uuid.UUID, data: CopyNodeRequest) -> CopyResultResponse:
        """Faylni nusxalash."""
        if not await self.cfs.exists(data.source_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source not found: {data.source_path}",
            )

        dest_raw = await self.cfs.stat_path(data.dest_parent_path)
        if dest_raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination not found: {data.dest_parent_path}",
            )
        if dest_raw.get("type") != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination is not a directory",
            )

        # Nom unikal qilish
        source_name = data.source_path.rsplit("/", 1)[-1]
        unique_name = await self.cfs.generate_unique_name(data.dest_parent_path, source_name)

        # Agar nom o'zgarsa, nusxa yaratib keyin rename
        new_vfs = await self.cfs.copy(data.source_path, data.dest_parent_path)
        if unique_name != source_name:
            # Nusxa source_name bilan yaratildi, uni rename qilish kerak
            dest_vfs = (
                f"/{source_name}"
                if data.dest_parent_path == "/"
                else f"{data.dest_parent_path}/{source_name}"
            )
            final_vfs = (
                f"/{unique_name}"
                if data.dest_parent_path == "/"
                else f"{data.dest_parent_path}/{unique_name}"
            )
            await self.cfs.rename(dest_vfs, final_vfs)
            new_vfs = final_vfs

        raw = await self.cfs.stat_path(new_vfs)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Copied but stat failed",
            )

        return CopyResultResponse(
            source_path=data.source_path,
            new_path=new_vfs,
            node=_build_node_response(raw, user_id, new_vfs, self.cfs.base_path),
        )

    async def delete_node(self, user_id: uuid.UUID, data: DeleteNodeRequest) -> FileNodeResponse:
        """Faylni o'chirish (trash yoki permanent)."""
        if data.path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete root",
            )

        # O'chirishdan oldin stat olish
        raw = await self.cfs.stat_path(data.path)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node not found: {data.path}",
            )

        response = _build_node_response(raw, user_id, data.path, self.cfs.base_path)

        if data.permanent:
            # To'liq o'chirish
            await self.cfs.delete(data.path)
            await self._delete_metadata(user_id, data.path)
        else:
            # Trash ga ko'chirish
            trash_vfs = await self.cfs.move_to_trash(data.path)
            # DB'ga original_path saqlash (restore uchun)
            await self._upsert_metadata(
                user_id,
                trash_vfs,
                is_trashed=True,
                original_path=data.path,
            )
            # Eski path metadata ni o'chirish
            await self._delete_metadata(user_id, data.path)

            response.is_trashed = True
            response.original_path = data.path
            response.path = trash_vfs

        return response

    async def bulk_delete(self, user_id: uuid.UUID, data: BulkDeleteRequest) -> BulkResultResponse:
        """Ko'plab fayllarni o'chirish."""
        succeeded: list[str] = []
        failed: list[dict[str, str | None]] = []

        for path in data.paths:
            try:
                await self.delete_node(
                    user_id, DeleteNodeRequest(path=path, permanent=data.permanent)
                )
                succeeded.append(path)
            except HTTPException as e:
                failed.append({"path": path, "error": e.detail})

        return BulkResultResponse(
            succeeded=succeeded,
            failed=[{"path": f["path"], "error": f["error"]} for f in failed],  # type: ignore[misc]
        )

    async def bulk_move(self, user_id: uuid.UUID, data: BulkMoveRequest) -> BulkResultResponse:
        """Ko'plab fayllarni ko'chirish."""
        succeeded: list[str] = []
        failed: list[dict[str, str | None]] = []

        for path in data.source_paths:
            try:
                await self.move_node(
                    user_id,
                    MoveNodeRequest(source_path=path, dest_parent_path=data.dest_parent_path),
                )
                succeeded.append(path)
            except HTTPException as e:
                failed.append({"path": path, "error": e.detail})

        return BulkResultResponse(
            succeeded=succeeded,
            failed=[{"path": f["path"], "error": f["error"]} for f in failed],  # type: ignore[misc]
        )

    async def list_trash(self, user_id: uuid.UUID) -> list[FileNodeResponse]:
        """Trash ichidagi fayllar ro'yxati."""
        try:
            children_raw = await self.cfs.list_directory("/.Trash")
        except HTTPException:
            return []

        # DB'dan original_path ma'lumotlarini olish
        trash_meta = await self._get_trash_metadata(user_id)

        results: list[FileNodeResponse] = []
        for child in children_raw:
            child_container_path = child.get("path", "")
            if child_container_path.startswith(self.cfs.base_path + "/"):
                child_vfs = child_container_path[len(self.cfs.base_path) :]
            else:
                child_vfs = child_container_path

            meta = trash_meta.get(child_vfs)
            results.append(
                _build_node_response(
                    child,
                    user_id,
                    child_vfs,
                    self.cfs.base_path,
                    is_trashed=True,
                    original_path=meta.original_path if meta else None,
                )
            )

        return results

    async def restore_node(
        self, user_id: uuid.UUID, data: RestoreNodeRequest
    ) -> MoveResultResponse:
        """Trash'dan faylni tiklash."""
        # DB'dan original_path olish
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == data.path,
                FileSystemNode.is_trashed == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        meta = result.scalar_one_or_none()

        if meta is None or not meta.original_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Original path unknown, cannot restore",
            )

        original_path = meta.original_path
        parent_path = original_path.rsplit("/", 1)[0] or "/"

        # Parent mavjudligini tekshirish
        if not await self.cfs.exists(parent_path):
            await self.cfs.create_directory(parent_path)

        # Unikal nom
        name = original_path.rsplit("/", 1)[-1]
        unique_name = await self.cfs.generate_unique_name(parent_path, name)
        new_path = f"/{unique_name}" if parent_path == "/" else f"{parent_path}/{unique_name}"

        # Container ichida ko'chirish (rename VFS pathlar bilan ishlaydi)
        source_container = self.cfs._vfs_to_container(data.path)
        dest_container = self.cfs._vfs_to_container(new_path)
        _, exit_code = await self.cfs._exec_cmd(["mv", source_container, dest_container])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to restore: {data.path}",
            )

        # DB metadata tozalash
        await self._delete_metadata(user_id, data.path)

        raw = await self.cfs.stat_path(new_path)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Restored but stat failed",
            )

        return MoveResultResponse(
            old_path=data.path,
            new_path=new_path,
            node=_build_node_response(raw, user_id, new_path, self.cfs.base_path),
        )

    async def empty_trash(self, user_id: uuid.UUID) -> int:
        """Trash'ni tozalash."""
        count = await self.cfs.empty_trash()

        # DB'dan barcha trash metadata ni o'chirish
        await self.db.execute(
            delete(FileSystemNode).where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.is_trashed == True,  # noqa: E712
                )
            )
        )
        await self.db.flush()

        return count

    async def update_desktop_positions(
        self,
        user_id: uuid.UUID,
        data: BatchUpdateDesktopPositionsRequest,
    ) -> list[FileNodeResponse]:
        """Desktop pozitsiyalarni yangilash."""
        results: list[FileNodeResponse] = []

        for pos in data.positions:
            raw = await self.cfs.stat_path(pos.path)
            if not raw:
                continue

            await self._upsert_metadata(user_id, pos.path, desktop_x=pos.x, desktop_y=pos.y)

            results.append(
                _build_node_response(
                    raw,
                    user_id,
                    pos.path,
                    self.cfs.base_path,
                    desktop_x=pos.x,
                    desktop_y=pos.y,
                )
            )

        return results

    async def search(
        self, user_id: uuid.UUID, query: str, scope_path: str | None = None
    ) -> list[FileNodeResponse]:
        """Fayl nomi bo'yicha qidirish."""
        scope = scope_path or "/"
        raw_results = await self.cfs.search(query, scope)

        results: list[FileNodeResponse] = []
        for raw in raw_results:
            container_path = raw.get("path", "")
            if container_path.startswith(self.cfs.base_path + "/"):
                vfs_path = container_path[len(self.cfs.base_path) :]
            elif container_path == self.cfs.base_path:
                vfs_path = "/"
            else:
                vfs_path = container_path

            results.append(_build_node_response(raw, user_id, vfs_path, self.cfs.base_path))

        return results
