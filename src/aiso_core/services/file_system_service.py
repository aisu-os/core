from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiso_core.models.file_system_node import FileSystemNode
from aiso_core.schemas.file_system import (
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

DEFAULT_DIRS = [
    "/",
    "/Desktop",
    "/Documents",
    "/Downloads",
    "/Pictures",
    "/Music",
    "/Videos",
    "/.Trash",
]


async def seed_user_file_system(db: AsyncSession, user_id: uuid.UUID) -> None:
    root_node: FileSystemNode | None = None

    for dir_path in DEFAULT_DIRS:
        name = "/" if dir_path == "/" else dir_path.rsplit("/", 1)[-1]
        parent_id: uuid.UUID | None = None

        if dir_path != "/":
            parent_path = dir_path.rsplit("/", 1)[0] or "/"
            parent_stmt = select(FileSystemNode).where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.path == parent_path,
                )
            )
            parent_result = await db.execute(parent_stmt)
            parent = parent_result.scalar_one_or_none()
            if parent:
                parent_id = parent.id

        if root_node is None and dir_path == "/":
            node = FileSystemNode(
                user_id=user_id,
                parent_id=None,
                name=name,
                path=dir_path,
                node_type="directory",
            )
            db.add(node)
            await db.flush()
            root_node = node
        else:
            node = FileSystemNode(
                user_id=user_id,
                parent_id=parent_id,
                name=name,
                path=dir_path,
                node_type="directory",
            )
            db.add(node)
            await db.flush()


class FileSystemService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Internal helpers ──

    async def _get_node_or_404(self, user_id: uuid.UUID, path: str) -> FileSystemNode:
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == path,
                FileSystemNode.is_trashed == False,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        node = result.scalar_one_or_none()
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node not found: {path}",
            )
        return node

    def _build_path(self, parent_path: str, name: str) -> str:
        if parent_path == "/":
            return f"/{name}"
        return f"{parent_path}/{name}"

    async def _generate_unique_name(
        self, user_id: uuid.UUID, parent_path: str, base_name: str
    ) -> str:
        select(FileSystemNode.name).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path.like(f"{parent_path}/%" if parent_path != "/" else "/%"),
            )
        )
        # Get direct children names only
        parent = await self._get_node_or_404(user_id, parent_path)
        children_stmt = select(FileSystemNode.name).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.parent_id == parent.id,
                FileSystemNode.is_trashed == False,  # noqa: E712
            )
        )
        result = await self.db.execute(children_stmt)
        existing = {row[0].lower() for row in result.all()}

        if base_name.lower() not in existing:
            return base_name

        counter = 2
        while f"{base_name} {counter}".lower() in existing:
            counter += 1
        return f"{base_name} {counter}"

    async def _rewrite_descendant_paths(
        self, user_id: uuid.UUID, old_prefix: str, new_prefix: str
    ) -> None:
        if old_prefix == new_prefix:
            return
        stmt = (
            update(FileSystemNode)
            .where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.path.like(f"{old_prefix}/%"),
                )
            )
            .values(
                path=func.concat(new_prefix, func.substr(FileSystemNode.path, len(old_prefix) + 1))
            )
        )
        await self.db.execute(stmt)

    # ── Public API ──

    async def get_tree(self, user_id: uuid.UUID) -> FileNodeTreeResponse:
        # Check root exists, lazy seed if not
        root_stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == "/",
            )
        )
        result = await self.db.execute(root_stmt)
        root = result.scalar_one_or_none()

        if root is None:
            await seed_user_file_system(self.db, user_id)
            result = await self.db.execute(root_stmt)
            root = result.scalar_one_or_none()

        # Fetch all non-trashed nodes
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.is_trashed == False,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()

        # Build tree in Python
        node_map: dict[uuid.UUID, FileNodeTreeResponse] = {}
        for n in nodes:
            node_map[n.id] = FileNodeTreeResponse(
                id=n.id,
                name=n.name,
                path=n.path,
                node_type=n.node_type,
                mime_type=n.mime_type,
                size=n.size,
                is_trashed=n.is_trashed,
                created_at=n.created_at,
                updated_at=n.updated_at,
                children=[],
            )

        root_response: FileNodeTreeResponse | None = None
        for n in nodes:
            resp = node_map[n.id]
            if n.parent_id and n.parent_id in node_map:
                node_map[n.parent_id].children.append(resp)
            elif n.path == "/":
                root_response = resp

        if root_response is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Root node not found after seeding",
            )
        return root_response

    async def get_node(self, user_id: uuid.UUID, path: str) -> FileNodeResponse:
        node = await self._get_node_or_404(user_id, path)
        return FileNodeResponse.model_validate(node)

    async def list_directory(
        self,
        user_id: uuid.UUID,
        path: str,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> DirectoryListingResponse:
        parent = await self._get_node_or_404(user_id, path)
        if parent.node_type != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not a directory",
            )

        order_col = {
            "name": FileSystemNode.name,
            "size": FileSystemNode.size,
            "created_at": FileSystemNode.created_at,
            "updated_at": FileSystemNode.updated_at,
        }.get(sort_by, FileSystemNode.name)

        order = order_col.asc() if sort_dir == "asc" else order_col.desc()

        stmt = (
            select(FileSystemNode)
            .where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.parent_id == parent.id,
                    FileSystemNode.is_trashed == False,  # noqa: E712
                )
            )
            .order_by(order)
        )
        result = await self.db.execute(stmt)
        children = result.scalars().all()

        return DirectoryListingResponse(
            path=path,
            node=FileNodeResponse.model_validate(parent),
            children=[FileNodeResponse.model_validate(c) for c in children],
            total=len(children),
        )

    async def create_node(self, user_id: uuid.UUID, data: CreateNodeRequest) -> FileNodeResponse:
        parent = await self._get_node_or_404(user_id, data.parent_path)
        if parent.node_type != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent is not a directory",
            )

        unique_name = await self._generate_unique_name(user_id, data.parent_path, data.name)
        new_path = self._build_path(data.parent_path, unique_name)

        node = FileSystemNode(
            user_id=user_id,
            parent_id=parent.id,
            name=unique_name,
            path=new_path,
            node_type=data.node_type,
            mime_type=data.mime_type,
            size=data.size,
        )
        self.db.add(node)
        await self.db.flush()
        await self.db.refresh(node)

        return FileNodeResponse.model_validate(node)

    async def rename_node(self, user_id: uuid.UUID, data: RenameNodeRequest) -> MoveResultResponse:
        node = await self._get_node_or_404(user_id, data.path)
        if data.path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rename root",
            )

        old_path = node.path
        parent_path = old_path.rsplit("/", 1)[0] or "/"
        new_path = self._build_path(parent_path, data.new_name)

        # Check uniqueness
        existing_stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == new_path,
                FileSystemNode.is_trashed == False,  # noqa: E712
            )
        )
        result = await self.db.execute(existing_stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Name already exists: {data.new_name}",
            )

        # Update descendants first
        await self._rewrite_descendant_paths(user_id, old_path, new_path)

        # Update the node itself
        node.name = data.new_name
        node.path = new_path
        await self.db.flush()
        await self.db.refresh(node)

        return MoveResultResponse(
            old_path=old_path,
            new_path=new_path,
            node=FileNodeResponse.model_validate(node),
        )

    async def move_node(self, user_id: uuid.UUID, data: MoveNodeRequest) -> MoveResultResponse:
        node = await self._get_node_or_404(user_id, data.source_path)
        if data.source_path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move root",
            )

        # Cannot move into itself
        if data.dest_parent_path == data.source_path or data.dest_parent_path.startswith(
            data.source_path + "/"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move into itself or its descendant",
            )

        dest_parent = await self._get_node_or_404(user_id, data.dest_parent_path)
        if dest_parent.node_type != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination is not a directory",
            )

        old_path = node.path
        unique_name = await self._generate_unique_name(user_id, data.dest_parent_path, node.name)
        new_path = self._build_path(data.dest_parent_path, unique_name)

        # Rewrite descendants
        await self._rewrite_descendant_paths(user_id, old_path, new_path)

        # Update node
        node.parent_id = dest_parent.id
        node.name = unique_name
        node.path = new_path
        await self.db.flush()
        await self.db.refresh(node)

        return MoveResultResponse(
            old_path=old_path,
            new_path=new_path,
            node=FileNodeResponse.model_validate(node),
        )

    async def copy_node(self, user_id: uuid.UUID, data: CopyNodeRequest) -> CopyResultResponse:
        source = await self._get_node_or_404(user_id, data.source_path)
        dest_parent = await self._get_node_or_404(user_id, data.dest_parent_path)
        if dest_parent.node_type != "directory":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination is not a directory",
            )

        unique_name = await self._generate_unique_name(user_id, data.dest_parent_path, source.name)
        new_root_path = self._build_path(data.dest_parent_path, unique_name)

        # Deep copy: get source + all descendants
        descendants_stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path.like(f"{data.source_path}/%"),
                FileSystemNode.is_trashed == False,  # noqa: E712
            )
        )
        result = await self.db.execute(descendants_stmt)
        descendants = result.scalars().all()

        # Create root copy
        root_copy = FileSystemNode(
            user_id=user_id,
            parent_id=dest_parent.id,
            name=unique_name,
            path=new_root_path,
            node_type=source.node_type,
            mime_type=source.mime_type,
            size=source.size,
            content_ref=source.content_ref,
        )
        self.db.add(root_copy)
        await self.db.flush()

        # Map old IDs to new IDs for parent_id resolution
        id_map: dict[uuid.UUID, uuid.UUID] = {source.id: root_copy.id}

        for desc in descendants:
            new_desc_path = new_root_path + desc.path[len(data.source_path) :]
            new_parent_id = id_map.get(desc.parent_id) if desc.parent_id else None

            copy = FileSystemNode(
                user_id=user_id,
                parent_id=new_parent_id,
                name=desc.name,
                path=new_desc_path,
                node_type=desc.node_type,
                mime_type=desc.mime_type,
                size=desc.size,
                content_ref=desc.content_ref,
            )
            self.db.add(copy)
            await self.db.flush()
            id_map[desc.id] = copy.id

        await self.db.refresh(root_copy)

        return CopyResultResponse(
            source_path=data.source_path,
            new_path=new_root_path,
            node=FileNodeResponse.model_validate(root_copy),
        )

    async def delete_node(self, user_id: uuid.UUID, data: DeleteNodeRequest) -> FileNodeResponse:
        node = await self._get_node_or_404(user_id, data.path)
        if data.path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete root",
            )

        if data.permanent:
            # Hard delete — remove from DB
            await self.db.execute(
                delete(FileSystemNode).where(
                    and_(
                        FileSystemNode.user_id == user_id,
                        FileSystemNode.path.like(f"{data.path}/%"),
                    )
                )
            )
            response = FileNodeResponse.model_validate(node)
            await self.db.delete(node)
            await self.db.flush()
            return response

        # Soft delete — move to trash
        now = datetime.now(UTC)
        trash_path = f"/.Trash/{node.name}"

        # Ensure unique name in trash
        trash_parent = await self._get_node_or_404(user_id, "/.Trash")
        unique_name = await self._generate_unique_name(user_id, "/.Trash", node.name)
        trash_path = self._build_path("/.Trash", unique_name)

        # Mark descendants as trashed
        await self.db.execute(
            update(FileSystemNode)
            .where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.path.like(f"{data.path}/%"),
                )
            )
            .values(is_trashed=True, trashed_at=now)
        )

        # Rewrite descendant paths
        await self._rewrite_descendant_paths(user_id, data.path, trash_path)

        # Update the node itself
        node.original_path = data.path
        node.is_trashed = True
        node.trashed_at = now
        node.parent_id = trash_parent.id
        node.name = unique_name
        node.path = trash_path
        await self.db.flush()
        await self.db.refresh(node)

        return FileNodeResponse.model_validate(node)

    async def bulk_delete(self, user_id: uuid.UUID, data: BulkDeleteRequest) -> BulkResultResponse:
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
        trash = await self._get_node_or_404(user_id, "/.Trash")
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.parent_id == trash.id,
                FileSystemNode.is_trashed == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()
        return [FileNodeResponse.model_validate(n) for n in nodes]

    async def restore_node(
        self, user_id: uuid.UUID, data: RestoreNodeRequest
    ) -> MoveResultResponse:
        # Find node in trash (trashed nodes)
        stmt = select(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.path == data.path,
                FileSystemNode.is_trashed == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        node = result.scalar_one_or_none()
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trashed node not found: {data.path}",
            )

        original_path = node.original_path
        if not original_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Original path unknown, cannot restore",
            )

        # Determine parent from original path
        parent_path = original_path.rsplit("/", 1)[0] or "/"
        parent = await self._get_node_or_404(user_id, parent_path)

        unique_name = await self._generate_unique_name(user_id, parent_path, node.name)
        new_path = self._build_path(parent_path, unique_name)

        old_path = node.path

        # Un-trash descendants
        await self.db.execute(
            update(FileSystemNode)
            .where(
                and_(
                    FileSystemNode.user_id == user_id,
                    FileSystemNode.path.like(f"{old_path}/%"),
                )
            )
            .values(is_trashed=False, trashed_at=None)
        )

        # Rewrite descendant paths
        await self._rewrite_descendant_paths(user_id, old_path, new_path)

        # Update the node
        node.parent_id = parent.id
        node.name = unique_name
        node.path = new_path
        node.is_trashed = False
        node.trashed_at = None
        node.original_path = None
        await self.db.flush()
        await self.db.refresh(node)

        return MoveResultResponse(
            old_path=old_path,
            new_path=new_path,
            node=FileNodeResponse.model_validate(node),
        )

    async def empty_trash(self, user_id: uuid.UUID) -> int:
        stmt = delete(FileSystemNode).where(
            and_(
                FileSystemNode.user_id == user_id,
                FileSystemNode.is_trashed == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount  # type: ignore[return-value]

    async def search(
        self, user_id: uuid.UUID, query: str, scope_path: str | None = None
    ) -> list[FileNodeResponse]:
        conditions = [
            FileSystemNode.user_id == user_id,
            FileSystemNode.is_trashed == False,  # noqa: E712
            FileSystemNode.name.ilike(f"%{query}%"),
        ]
        if scope_path:
            conditions.append(FileSystemNode.path.like(f"{scope_path}/%"))

        stmt = select(FileSystemNode).where(and_(*conditions)).limit(50)
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()
        return [FileNodeResponse.model_validate(n) for n in nodes]
