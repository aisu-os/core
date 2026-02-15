from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from aiso_core.config import settings
from aiso_core.database import get_db
from aiso_core.main import app
from aiso_core.models.beta_access_request import BetaAccessRequest
from aiso_core.models.container_event import ContainerEvent
from aiso_core.models.file_system_node import FileSystemNode
from aiso_core.models.user import User
from aiso_core.models.user_container import UserContainer
from aiso_core.services.beta_access_service import BetaAccessService
from aiso_core.utils.rate_limiter import get_rate_limiter


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(element: UUID, compiler, **kw) -> str:  # type: ignore[no-untyped-def]
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element: JSONB, compiler, **kw) -> str:  # type: ignore[no-untyped-def]
    return "JSON"


@pytest.fixture
async def db_engine(tmp_path_factory) -> AsyncGenerator:
    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: User.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(
            lambda sync_conn: BetaAccessRequest.__table__.create(sync_conn, checkfirst=True)
        )
        await conn.run_sync(
            lambda sync_conn: FileSystemNode.__table__.create(sync_conn, checkfirst=True)
        )
        await conn.run_sync(
            lambda sync_conn: UserContainer.__table__.create(sync_conn, checkfirst=True)
        )
        await conn.run_sync(
            lambda sync_conn: ContainerEvent.__table__.create(sync_conn, checkfirst=True)
        )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def async_session_factory(
    db_engine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    yield async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
async def db_session(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


@pytest.fixture
def beta_token_store() -> dict[str, str]:
    return {}


class _LocalFsService:
    """Test uchun Docker o'rniga lokal fayl tizimida ishlaydigan ContainerFsService."""

    def __init__(self, _container_name: str, base_path: str = "/home/aisu"):
        # base_path test vaqtida _fs_root bilan almashtiriladi
        self.base_path = base_path

    # -- path helpers --

    def _vfs_to_container(self, vfs_path: str) -> str:
        if vfs_path == "/":
            return self.base_path
        return self.base_path + vfs_path

    def _container_to_vfs(self, container_path: str) -> str:
        if container_path == self.base_path or container_path == self.base_path + "/":
            return "/"
        if container_path.startswith(self.base_path + "/"):
            return container_path[len(self.base_path) :]
        return container_path

    # -- read ops --

    async def get_tree(self, max_depth: int = 10) -> dict:
        import mimetypes
        import os

        def _tree(path: str, depth: int = 0) -> list[dict]:
            result = []
            if depth > max_depth:
                return result
            try:
                entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
            except (PermissionError, FileNotFoundError):
                return result
            for entry in entries:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                mime, _ = mimetypes.guess_type(entry.name)
                is_dir = entry.is_dir(follow_symlinks=False)
                node: dict = {
                    "name": entry.name,
                    "path": entry.path,
                    "type": "directory" if is_dir else "file",
                    "size": 0 if is_dir else st.st_size,
                    "mime_type": mime,
                    "mtime": st.st_mtime,
                    "ctime": st.st_ctime,
                }
                if is_dir:
                    node["children"] = _tree(entry.path, depth + 1)
                result.append(node)
            return result

        st = os.stat(self.base_path)
        return {
            "name": "/",
            "path": self.base_path,
            "type": "directory",
            "size": 0,
            "mime_type": None,
            "mtime": st.st_mtime,
            "ctime": st.st_ctime,
            "children": _tree(self.base_path),
        }

    async def list_directory(self, vfs_path: str) -> list[dict]:
        import mimetypes
        import os

        container_path = self._vfs_to_container(vfs_path)
        if not os.path.isdir(container_path):
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Directory not found: {vfs_path}",
            )
        entries = sorted(os.scandir(container_path), key=lambda e: (not e.is_dir(), e.name.lower()))
        result = []
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            mime, _ = mimetypes.guess_type(entry.name)
            is_dir = entry.is_dir(follow_symlinks=False)
            result.append(
                {
                    "name": entry.name,
                    "path": entry.path,
                    "type": "directory" if is_dir else "file",
                    "size": 0 if is_dir else st.st_size,
                    "mime_type": mime,
                    "mtime": st.st_mtime,
                    "ctime": st.st_ctime,
                }
            )
        return result

    async def stat_path(self, vfs_path: str) -> dict | None:
        import mimetypes
        import os

        container_path = self._vfs_to_container(vfs_path)
        try:
            st = os.stat(container_path)
        except (FileNotFoundError, PermissionError):
            return None
        is_dir = os.path.isdir(container_path)
        name = os.path.basename(container_path) or "/"
        mime, _ = mimetypes.guess_type(name)
        return {
            "name": name,
            "path": container_path,
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else st.st_size,
            "mime_type": mime,
            "mtime": st.st_mtime,
            "ctime": st.st_ctime,
        }

    async def exists(self, vfs_path: str) -> bool:
        import os

        return os.path.exists(self._vfs_to_container(vfs_path))

    async def search(self, query: str, scope_vfs: str = "/") -> list[dict]:
        import mimetypes
        import os

        scope_path = self._vfs_to_container(scope_vfs)
        results = []
        q = query.lower()
        for root, dirs, files in os.walk(scope_path):
            for name in dirs + files:
                if q in name.lower():
                    full = os.path.join(root, name)
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    is_dir = os.path.isdir(full)
                    mime, _ = mimetypes.guess_type(name)
                    results.append(
                        {
                            "name": name,
                            "path": full,
                            "type": "directory" if is_dir else "file",
                            "size": 0 if is_dir else st.st_size,
                            "mime_type": mime,
                            "mtime": st.st_mtime,
                            "ctime": st.st_ctime,
                        }
                    )
                    if len(results) >= 50:
                        return results
        return results

    async def read_file(self, vfs_path: str, max_size: int = 2 * 1024 * 1024) -> dict:
        import os

        from fastapi import HTTPException, status

        container_path = self._vfs_to_container(vfs_path)
        if not os.path.exists(container_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {vfs_path}",
            )
        if os.path.isdir(container_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Path is a directory: {vfs_path}",
            )

        size = os.path.getsize(container_path)
        if size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large: {size} bytes (max {max_size})",
            )

        try:
            with open(container_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Binary file cannot be opened as text: {vfs_path}",
            )

        return {"content": content, "size": size, "encoding": "utf-8"}

    # -- write ops --

    async def create_file(self, vfs_path: str) -> None:
        container_path = self._vfs_to_container(vfs_path)
        Path(container_path).touch()

    async def create_directory(self, vfs_path: str) -> None:
        container_path = self._vfs_to_container(vfs_path)
        Path(container_path).mkdir(parents=True, exist_ok=True)

    async def rename(self, old_vfs: str, new_vfs: str) -> None:
        import os

        os.rename(self._vfs_to_container(old_vfs), self._vfs_to_container(new_vfs))

    async def move(self, source_vfs: str, dest_parent_vfs: str) -> str:
        import shutil

        source = self._vfs_to_container(source_vfs)
        dest_dir = self._vfs_to_container(dest_parent_vfs)
        name = source_vfs.rsplit("/", 1)[-1]
        shutil.move(source, dest_dir + "/")
        return f"/{name}" if dest_parent_vfs == "/" else f"{dest_parent_vfs}/{name}"

    async def copy(self, source_vfs: str, dest_parent_vfs: str) -> str:
        import shutil

        source = self._vfs_to_container(source_vfs)
        dest_dir = self._vfs_to_container(dest_parent_vfs)
        name = source_vfs.rsplit("/", 1)[-1]
        dest = dest_dir + "/" + name
        if Path(source).is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        return f"/{name}" if dest_parent_vfs == "/" else f"{dest_parent_vfs}/{name}"

    async def write_file(self, vfs_path: str, content: str) -> None:
        import os

        container_path = self._vfs_to_container(vfs_path)
        parent = os.path.dirname(container_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(container_path, "w", encoding="utf-8") as f:
            f.write(content)

    async def delete(self, vfs_path: str) -> None:
        import shutil

        p = Path(self._vfs_to_container(vfs_path))
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)

    async def move_to_trash(self, vfs_path: str) -> str:
        name = vfs_path.rsplit("/", 1)[-1]
        trash_vfs = f"/.Trash/{name}"
        if await self.exists(trash_vfs):
            counter = 2
            while await self.exists(f"/.Trash/{name} {counter}"):
                counter += 1
            name = f"{name} {counter}"
            trash_vfs = f"/.Trash/{name}"
        await self.create_directory("/.Trash")
        import os

        os.rename(
            self._vfs_to_container(vfs_path),
            self._vfs_to_container(trash_vfs),
        )
        return trash_vfs

    async def empty_trash(self) -> int:
        import shutil

        items = await self.list_directory("/.Trash")
        count = len(items)
        if count > 0:
            trash = Path(self._vfs_to_container("/.Trash"))
            for child in trash.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        return count

    async def _exec_cmd(self, cmd: list[str]) -> tuple[str, int]:
        """Lokal subprocess orqali buyruq bajarish."""
        import subprocess

        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.returncode

    async def generate_unique_name(self, parent_vfs: str, base_name: str) -> str:
        check_path = f"{parent_vfs}/{base_name}" if parent_vfs != "/" else f"/{base_name}"
        if not await self.exists(check_path):
            return base_name
        counter = 2
        while True:
            candidate = f"{base_name} {counter}"
            check_path = f"{parent_vfs}/{candidate}" if parent_vfs != "/" else f"/{candidate}"
            if not await self.exists(check_path):
                return candidate
            counter += 1


# Har bir test sessiyasi uchun alohida fs root yaratish
_fs_roots: dict[str, str] = {}


def _make_local_fs_service(tmp_base: str):
    """Factory: container_name ga qarab LocalFsService qaytaruvchi wrapper."""

    original_init = _LocalFsService.__init__

    def _patched_init(self, container_name: str, base_path: str = "/home/aisu"):
        original_init(self, container_name, base_path)
        if container_name not in _fs_roots:
            user_dir = Path(tmp_base) / container_name
            for d in ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", ".Trash"]:
                (user_dir / d).mkdir(parents=True, exist_ok=True)
            _fs_roots[container_name] = str(user_dir)
        self.base_path = _fs_roots[container_name]

    _LocalFsService.__init__ = _patched_init  # type: ignore[assignment]
    return _LocalFsService


@pytest.fixture
async def client(
    async_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    beta_token_store: dict[str, str],
) -> AsyncGenerator[AsyncClient, None]:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "app_url", "http://testserver")
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    monkeypatch.setattr(settings, "container_enabled", False)
    monkeypatch.setattr(settings, "beta_access_enabled", True)
    get_rate_limiter.cache_clear()

    async def capture_beta_email(
        _service: BetaAccessService,
        recipient_email: str,
        token: str,
    ) -> None:
        beta_token_store[recipient_email] = token

    monkeypatch.setattr(BetaAccessService, "_send_access_email", capture_beta_email)

    # ContainerFsService ni lokal fayl tizimida ishlaydigan versiya bilan almashtirish
    _fs_roots.clear()
    fs_base = str(tmp_path / "fs")
    Path(fs_base).mkdir(exist_ok=True)
    LocalFs = _make_local_fs_service(fs_base)
    monkeypatch.setattr(
        "aiso_core.services.file_system_service.ContainerFsService",
        LocalFs,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
