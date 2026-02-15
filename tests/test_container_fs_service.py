"""ContainerFsService unit testlari.

conftest.py dagi _LocalFsService orqali Docker kerak emas —
lokal fayl tizimida ishlaydi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from aiso_core.services.container_fs_service import ContainerFsService, _validate_path

# ── _validate_path testlari ──


class TestValidatePath:
    def test_normal_path(self) -> None:
        _validate_path("/Documents/test.txt")

    def test_root_path(self) -> None:
        _validate_path("/")

    def test_nested_path(self) -> None:
        _validate_path("/Desktop/folder/subfolder/file.txt")

    def test_dotdot_raises(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _validate_path("/Documents/../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_dotdot_at_start_raises(self) -> None:
        with pytest.raises(HTTPException):
            _validate_path("/../secret")

    def test_single_dot_allowed(self) -> None:
        _validate_path("/Documents/./file.txt")  # "." bitta nuqta ruxsat

    def test_dotdot_in_name_allowed(self) -> None:
        _validate_path("/Documents/my..file.txt")  # fayl nomida ".." ruxsat


# ── Path konvertatsiya testlari ──


class TestPathConversion:
    def test_vfs_to_container_root(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        assert svc._vfs_to_container("/") == "/home/aisu"

    def test_vfs_to_container_subpath(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        assert svc._vfs_to_container("/Documents") == "/home/aisu/Documents"

    def test_vfs_to_container_deep_path(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        assert svc._vfs_to_container("/Desktop/a/b") == "/home/aisu/Desktop/a/b"

    def test_container_to_vfs_root(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        assert svc._container_to_vfs("/home/aisu") == "/"
        assert svc._container_to_vfs("/home/aisu/") == "/"

    def test_container_to_vfs_subpath(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        assert svc._container_to_vfs("/home/aisu/Documents") == "/Documents"

    def test_container_to_vfs_unknown_path(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        assert svc._container_to_vfs("/etc/passwd") == "/etc/passwd"

    def test_vfs_to_container_traversal_blocked(self) -> None:
        svc = ContainerFsService("test_container", "/home/aisu")
        with pytest.raises(HTTPException):
            svc._vfs_to_container("/Documents/../../../etc/passwd")


# ── ContainerFsService operatsiyalari (lokal fayl tizimida) ──
# conftest.py dagi _LocalFsService ishlatilmaydi —
# to'g'ridan-to'g'ri ContainerFsService dagi path logikasi tekshiriladi.
# Docker-ga bog'liq metodlar uchun mock ishlatamiz.


class TestContainerFsOperations:
    """Lokal fayl tizimida ContainerFsService operatsiyalarini tekshirish.

    Docker exec o'rniga to'g'ridan-to'g'ri fayl tizimida ishlash uchun
    conftest.py dagi _LocalFsService uslubida tmp_path ishlatamiz.
    """

    @pytest.fixture
    def fs_root(self, tmp_path) -> Path:
        """Test uchun fayl tizimi root papkasi."""
        base = tmp_path / "home" / "aisu"
        for d in ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", ".Trash"]:
            (base / d).mkdir(parents=True)
        return base

    @pytest.fixture
    def local_fs(self, fs_root: Path):
        """Lokal fayl tizimida ishlaydigan mock service."""
        from tests.conftest import _LocalFsService

        svc = _LocalFsService.__new__(_LocalFsService)
        svc.container_name = "test_container"
        svc.base_path = str(fs_root)
        return svc

    # ── exists ──

    async def test_exists_root(self, local_fs) -> None:
        assert await local_fs.exists("/") is True

    async def test_exists_directory(self, local_fs) -> None:
        assert await local_fs.exists("/Desktop") is True

    async def test_exists_nonexistent(self, local_fs) -> None:
        assert await local_fs.exists("/nonexistent") is False

    # ── create_file ──

    async def test_create_file(self, local_fs, fs_root: Path) -> None:
        await local_fs.create_file("/Documents/test.txt")
        assert (fs_root / "Documents" / "test.txt").exists()

    # ── create_directory ──

    async def test_create_directory(self, local_fs, fs_root: Path) -> None:
        await local_fs.create_directory("/Documents/new_folder")
        assert (fs_root / "Documents" / "new_folder").is_dir()

    async def test_create_nested_directory(self, local_fs, fs_root: Path) -> None:
        await local_fs.create_directory("/Documents/a/b/c")
        assert (fs_root / "Documents" / "a" / "b" / "c").is_dir()

    # ── stat_path ──

    async def test_stat_file(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "hello.txt").write_text("hello world")
        result = await local_fs.stat_path("/Documents/hello.txt")
        assert result is not None
        assert result["type"] == "file"
        assert result["name"] == "hello.txt"
        assert result["size"] == 11

    async def test_stat_directory(self, local_fs) -> None:
        result = await local_fs.stat_path("/Desktop")
        assert result is not None
        assert result["type"] == "directory"

    async def test_stat_nonexistent(self, local_fs) -> None:
        result = await local_fs.stat_path("/nonexistent")
        assert result is None

    # ── list_directory ──

    async def test_list_directory_empty(self, local_fs) -> None:
        items = await local_fs.list_directory("/Desktop")
        assert isinstance(items, list)
        assert len(items) == 0

    async def test_list_directory_with_files(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "a.txt").touch()
        (fs_root / "Documents" / "b.txt").touch()
        items = await local_fs.list_directory("/Documents")
        names = [i["name"] for i in items]
        assert "a.txt" in names
        assert "b.txt" in names

    async def test_list_directory_not_found(self, local_fs) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await local_fs.list_directory("/nonexistent")
        assert exc_info.value.status_code == 404

    async def test_list_directory_dirs_first(self, local_fs, fs_root: Path) -> None:
        """Papkalar fayllardan oldin kelishi kerak."""
        (fs_root / "Desktop" / "subdir").mkdir()
        (fs_root / "Desktop" / "file.txt").touch()
        items = await local_fs.list_directory("/Desktop")
        assert items[0]["type"] == "directory"
        assert items[1]["type"] == "file"

    # ── rename ──

    async def test_rename_file(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "old.txt").write_text("content")
        await local_fs.rename("/Documents/old.txt", "/Documents/new.txt")
        assert not (fs_root / "Documents" / "old.txt").exists()
        assert (fs_root / "Documents" / "new.txt").read_text() == "content"

    # ── move ──

    async def test_move_file(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "moveme.txt").write_text("data")
        new_path = await local_fs.move("/Documents/moveme.txt", "/Desktop")
        assert new_path == "/Desktop/moveme.txt"
        assert not (fs_root / "Documents" / "moveme.txt").exists()
        assert (fs_root / "Desktop" / "moveme.txt").read_text() == "data"

    async def test_move_to_root(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "file.txt").touch()
        new_path = await local_fs.move("/Documents/file.txt", "/")
        assert new_path == "/file.txt"

    # ── copy ──

    async def test_copy_file(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "original.txt").write_text("original")
        new_path = await local_fs.copy("/Documents/original.txt", "/Desktop")
        assert new_path == "/Desktop/original.txt"
        assert (fs_root / "Documents" / "original.txt").exists()  # original qolgan
        assert (fs_root / "Desktop" / "original.txt").read_text() == "original"

    async def test_copy_directory(self, local_fs, fs_root: Path) -> None:
        src = fs_root / "Documents" / "mydir"
        src.mkdir()
        (src / "file.txt").write_text("inside")
        new_path = await local_fs.copy("/Documents/mydir", "/Desktop")
        assert new_path == "/Desktop/mydir"
        assert (fs_root / "Desktop" / "mydir" / "file.txt").read_text() == "inside"

    # ── delete ──

    async def test_delete_file(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "delete_me.txt").touch()
        await local_fs.delete("/Documents/delete_me.txt")
        assert not (fs_root / "Documents" / "delete_me.txt").exists()

    async def test_delete_directory(self, local_fs, fs_root: Path) -> None:
        d = fs_root / "Documents" / "del_dir"
        d.mkdir()
        (d / "inner.txt").touch()
        await local_fs.delete("/Documents/del_dir")
        assert not d.exists()

    # ── move_to_trash ──

    async def test_move_to_trash(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "trash_me.txt").write_text("trash")
        trash_path = await local_fs.move_to_trash("/Documents/trash_me.txt")
        assert trash_path == "/.Trash/trash_me.txt"
        assert not (fs_root / "Documents" / "trash_me.txt").exists()
        assert (fs_root / ".Trash" / "trash_me.txt").read_text() == "trash"

    async def test_move_to_trash_duplicate_name(self, local_fs, fs_root: Path) -> None:
        """Agar Trash da bir xil nomli fayl bo'lsa, unikal nom yaratiladi."""
        (fs_root / ".Trash" / "dup.txt").touch()
        (fs_root / "Documents" / "dup.txt").touch()
        trash_path = await local_fs.move_to_trash("/Documents/dup.txt")
        assert trash_path == "/.Trash/dup.txt 2"

    # ── empty_trash ──

    async def test_empty_trash(self, local_fs, fs_root: Path) -> None:
        (fs_root / ".Trash" / "file1.txt").touch()
        (fs_root / ".Trash" / "file2.txt").touch()
        count = await local_fs.empty_trash()
        assert count == 2
        items = await local_fs.list_directory("/.Trash")
        assert len(items) == 0

    async def test_empty_trash_when_empty(self, local_fs) -> None:
        count = await local_fs.empty_trash()
        assert count == 0

    # ── search ──

    async def test_search_finds_file(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "report.pdf").touch()
        results = await local_fs.search("report")
        names = [r["name"] for r in results]
        assert "report.pdf" in names

    async def test_search_case_insensitive(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "MyFile.TXT").touch()
        results = await local_fs.search("myfile")
        assert len(results) >= 1
        assert results[0]["name"] == "MyFile.TXT"

    async def test_search_no_results(self, local_fs) -> None:
        results = await local_fs.search("nonexistent_file_xyz")
        assert len(results) == 0

    async def test_search_with_scope(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "scoped.txt").touch()
        (fs_root / "Desktop" / "scoped.txt").touch()
        results = await local_fs.search("scoped", scope_vfs="/Documents")
        assert len(results) == 1
        assert results[0]["name"] == "scoped.txt"

    # ── get_tree ──

    async def test_get_tree_returns_root(self, local_fs) -> None:
        tree = await local_fs.get_tree()
        assert tree["type"] == "directory"
        assert tree["name"] == "/"
        assert "children" in tree

    async def test_get_tree_includes_subdirs(self, local_fs) -> None:
        tree = await local_fs.get_tree()
        child_names = [c["name"] for c in tree["children"]]
        assert "Desktop" in child_names
        assert "Documents" in child_names

    async def test_get_tree_includes_files(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Desktop" / "note.txt").touch()
        tree = await local_fs.get_tree()
        desktop = next(c for c in tree["children"] if c["name"] == "Desktop")
        file_names = [c["name"] for c in desktop["children"]]
        assert "note.txt" in file_names

    # ── generate_unique_name ──

    async def test_generate_unique_name_no_conflict(self, local_fs) -> None:
        name = await local_fs.generate_unique_name("/Documents", "new_file.txt")
        assert name == "new_file.txt"

    async def test_generate_unique_name_with_conflict(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "file.txt").touch()
        name = await local_fs.generate_unique_name("/Documents", "file.txt")
        assert name == "file.txt 2"

    async def test_generate_unique_name_multiple_conflicts(self, local_fs, fs_root: Path) -> None:
        (fs_root / "Documents" / "file.txt").touch()
        (fs_root / "Documents" / "file.txt 2").touch()
        (fs_root / "Documents" / "file.txt 3").touch()
        name = await local_fs.generate_unique_name("/Documents", "file.txt")
        assert name == "file.txt 4"

    async def test_generate_unique_name_root(self, local_fs, fs_root: Path) -> None:
        (fs_root / "test.txt").touch()
        name = await local_fs.generate_unique_name("/", "test.txt")
        assert name == "test.txt 2"
