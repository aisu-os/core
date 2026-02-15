"""Docker container ichidagi fayl tizimi bilan ishlash servisi.

Container ichiga Docker exec orqali buyruqlar yuborib,
haqiqiy fayl tizimini boshqaradi.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex

from fastapi import HTTPException, status

from aiso_core.config import settings

logger = logging.getLogger(__name__)

# get_tree uchun container ichida bajariladigan Python script
_TREE_SCRIPT = """
import json, os, mimetypes, sys

def tree(path, depth=0, max_depth={max_depth}):
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
        node = {{
            "name": entry.name,
            "path": entry.path,
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else st.st_size,
            "mime_type": mime,
            "mtime": st.st_mtime,
            "ctime": st.st_ctime,
        }}
        if is_dir:
            node["children"] = tree(entry.path, depth + 1, max_depth)
        result.append(node)
    return result

base = "{base_path}"
try:
    st = os.stat(base)
    data = {{
        "name": "/",
        "path": base,
        "type": "directory",
        "size": 0,
        "mime_type": None,
        "mtime": st.st_mtime,
        "ctime": st.st_ctime,
        "children": tree(base),
    }}
    print(json.dumps(data))
except Exception as e:
    print(json.dumps({{"error": str(e)}}), file=sys.stderr)
    sys.exit(1)
"""

# list_directory uchun Python script
_LS_SCRIPT = """
import json, os, mimetypes, sys

path = "{container_path}"
try:
    entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
except FileNotFoundError:
    print(json.dumps({{"error": "not_found"}}))
    sys.exit(1)
except PermissionError:
    print(json.dumps({{"error": "permission_denied"}}))
    sys.exit(1)

result = []
for entry in entries:
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        continue
    mime, _ = mimetypes.guess_type(entry.name)
    is_dir = entry.is_dir(follow_symlinks=False)
    result.append({{
        "name": entry.name,
        "path": entry.path,
        "type": "directory" if is_dir else "file",
        "size": 0 if is_dir else st.st_size,
        "mime_type": mime,
        "mtime": st.st_mtime,
        "ctime": st.st_ctime,
    }})
print(json.dumps(result))
"""

# stat uchun Python script
_STAT_SCRIPT = """
import json, os, mimetypes, sys

path = "{container_path}"
try:
    st = os.stat(path)
    is_dir = os.path.isdir(path)
    name = os.path.basename(path) or "/"
    mime, _ = mimetypes.guess_type(name)
    print(json.dumps({{
        "name": name,
        "path": path,
        "type": "directory" if is_dir else "file",
        "size": 0 if is_dir else st.st_size,
        "mime_type": mime,
        "mtime": st.st_mtime,
        "ctime": st.st_ctime,
    }}))
except FileNotFoundError:
    print(json.dumps({{"error": "not_found"}}))
    sys.exit(1)
except PermissionError:
    print(json.dumps({{"error": "permission_denied"}}))
    sys.exit(1)
"""

# search uchun Python script
_SEARCH_SCRIPT = """
import json, os, mimetypes, sys

query = "{query}".lower()
scope = "{scope_path}"
results = []
max_results = 50

for root, dirs, files in os.walk(scope):
    for name in dirs + files:
        if query in name.lower():
            full_path = os.path.join(root, name)
            try:
                st = os.stat(full_path)
                is_dir = os.path.isdir(full_path)
                mime, _ = mimetypes.guess_type(name)
                results.append({{
                    "name": name,
                    "path": full_path,
                    "type": "directory" if is_dir else "file",
                    "size": 0 if is_dir else st.st_size,
                    "mime_type": mime,
                    "mtime": st.st_mtime,
                    "ctime": st.st_ctime,
                }})
                if len(results) >= max_results:
                    break
            except OSError:
                continue
    if len(results) >= max_results:
        break

print(json.dumps(results))
"""


def _get_docker_client():  # noqa: ANN202
    import docker

    return docker.DockerClient(base_url=settings.docker_base_url)


def _validate_path(vfs_path: str) -> None:
    """Path traversal hujumlarini oldini olish."""
    if ".." in vfs_path.split("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path '..' segmentini o'z ichiga olmaydi",
        )


class ContainerFsService:
    """Docker container ichidagi fayl tizimi bilan ishlash."""

    def __init__(self, container_name: str, base_path: str = "/home/aisu"):
        self.container_name = container_name
        self.base_path = base_path

    def _vfs_to_container(self, vfs_path: str) -> str:
        """VFS path ni container ichidagi absolut path ga o'giradi."""
        _validate_path(vfs_path)
        if vfs_path == "/":
            return self.base_path
        return self.base_path + vfs_path

    def _container_to_vfs(self, container_path: str) -> str:
        """Container absolut path ni VFS path ga o'giradi."""
        if container_path == self.base_path or container_path == self.base_path + "/":
            return "/"
        if container_path.startswith(self.base_path + "/"):
            return container_path[len(self.base_path) :]
        return container_path

    async def _exec_cmd(self, cmd: list[str]) -> tuple[str, int]:
        """Container ichida buyruq bajarish. (stdout, exit_code) qaytaradi."""
        client = _get_docker_client()

        exec_data = await asyncio.to_thread(
            client.api.exec_create,
            self.container_name,
            cmd=cmd,
            stdin=False,
            tty=False,
            user="aisu",
        )

        output = await asyncio.to_thread(
            client.api.exec_start,
            exec_data["Id"],
        )

        inspect = await asyncio.to_thread(
            client.api.exec_inspect,
            exec_data["Id"],
        )
        exit_code = inspect.get("ExitCode", -1)

        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace"), exit_code
        return str(output), exit_code

    async def _exec_python(self, script: str) -> str:
        """Container ichida Python script bajarish. stdout qaytaradi."""
        output, exit_code = await self._exec_cmd(
            ["python3", "-c", script],
        )

        if exit_code != 0:
            logger.error(
                "Python exec failed: container=%s exit=%d output=%s",
                self.container_name,
                exit_code,
                output[:500],
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Filesystem operation failed: {output[:200]}",
            )

        return output.strip()

    # ── O'qish operatsiyalari ──

    async def get_tree(self, max_depth: int = 10) -> dict:
        """Butun fayl tizimi daraxtini JSON sifatida olish."""
        script = _TREE_SCRIPT.format(
            base_path=self.base_path,
            max_depth=max_depth,
        )
        output = await self._exec_python(script)

        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.error("get_tree JSON parse error: %s", output[:500])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse filesystem tree",
            ) from exc

        if "error" in data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Filesystem error: {data['error']}",
            )

        return data

    async def list_directory(self, vfs_path: str) -> list[dict]:
        """Papka ichidagi fayllar ro'yxatini olish."""
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)

        script = _LS_SCRIPT.format(container_path=container_path)
        output = await self._exec_python(script)

        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.error("list_directory JSON parse error: %s", output[:500])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse directory listing",
            ) from exc

        if isinstance(data, dict) and "error" in data:
            if data["error"] == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Directory not found: {vfs_path}",
                )
            if data["error"] == "permission_denied":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {vfs_path}",
                )

        return data

    async def stat_path(self, vfs_path: str) -> dict | None:
        """Fayl/papka stat ma'lumotlarini olish."""
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)

        script = _STAT_SCRIPT.format(container_path=container_path)
        output, exit_code = await self._exec_cmd(
            ["python3", "-c", script],
        )
        if exit_code != 0:
            # not_found yoki permission_denied bo'lsa, None qaytaramiz
            return None

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return None

        if isinstance(data, dict) and "error" in data:
            return None

        return data

    async def exists(self, vfs_path: str) -> bool:
        """Path mavjudligini tekshirish."""
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)
        _, exit_code = await self._exec_cmd(["test", "-e", container_path])
        return exit_code == 0

    async def search(self, query: str, scope_vfs: str = "/") -> list[dict]:
        """Fayl nomi bo'yicha qidirish."""
        _validate_path(scope_vfs)
        scope_path = self._vfs_to_container(scope_vfs)

        # query ichida injection oldini olish
        safe_query = query.replace('"', '\\"').replace("'", "\\'")

        script = _SEARCH_SCRIPT.format(
            query=safe_query,
            scope_path=scope_path,
        )
        output = await self._exec_python(script)

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            logger.error("search JSON parse error: %s", output[:500])
            return []

    # ── Yozish operatsiyalari ──

    async def create_file(self, vfs_path: str) -> None:
        """Bo'sh fayl yaratish."""
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)
        _, exit_code = await self._exec_cmd(["touch", container_path])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create file: {vfs_path}",
            )

    async def create_directory(self, vfs_path: str) -> None:
        """Papka yaratish."""
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)
        _, exit_code = await self._exec_cmd(["mkdir", "-p", container_path])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create directory: {vfs_path}",
            )

    async def rename(self, old_vfs: str, new_vfs: str) -> None:
        """Fayl/papkani qayta nomlash."""
        _validate_path(old_vfs)
        _validate_path(new_vfs)
        old_path = self._vfs_to_container(old_vfs)
        new_path = self._vfs_to_container(new_vfs)
        _, exit_code = await self._exec_cmd(["mv", old_path, new_path])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to rename: {old_vfs} → {new_vfs}",
            )

    async def move(self, source_vfs: str, dest_parent_vfs: str) -> str:
        """Faylni boshqa papkaga ko'chirish. Yangi VFS path qaytaradi."""
        _validate_path(source_vfs)
        _validate_path(dest_parent_vfs)
        source_path = self._vfs_to_container(source_vfs)
        dest_path = self._vfs_to_container(dest_parent_vfs)
        _, exit_code = await self._exec_cmd(["mv", source_path, dest_path + "/"])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move: {source_vfs} → {dest_parent_vfs}",
            )
        # Yangi path: dest_parent + source_name
        source_name = source_vfs.rsplit("/", 1)[-1]
        if dest_parent_vfs == "/":
            return f"/{source_name}"
        return f"{dest_parent_vfs}/{source_name}"

    async def copy(self, source_vfs: str, dest_parent_vfs: str) -> str:
        """Faylni nusxalash. Yangi VFS path qaytaradi."""
        _validate_path(source_vfs)
        _validate_path(dest_parent_vfs)
        source_path = self._vfs_to_container(source_vfs)
        dest_path = self._vfs_to_container(dest_parent_vfs)
        _, exit_code = await self._exec_cmd(["cp", "-r", source_path, dest_path + "/"])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to copy: {source_vfs} → {dest_parent_vfs}",
            )
        source_name = source_vfs.rsplit("/", 1)[-1]
        if dest_parent_vfs == "/":
            return f"/{source_name}"
        return f"{dest_parent_vfs}/{source_name}"

    async def delete(self, vfs_path: str) -> None:
        """Faylni butunlay o'chirish."""
        _validate_path(vfs_path)
        if vfs_path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete root",
            )
        container_path = self._vfs_to_container(vfs_path)
        _, exit_code = await self._exec_cmd(["rm", "-rf", container_path])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete: {vfs_path}",
            )

    async def move_to_trash(self, vfs_path: str) -> str:
        """Faylni /.Trash/ ga ko'chirish. Trash ichidagi yangi VFS path qaytaradi."""
        _validate_path(vfs_path)
        if vfs_path == "/":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot trash root",
            )

        name = vfs_path.rsplit("/", 1)[-1]
        trash_vfs = f"/.Trash/{name}"
        trash_container = self._vfs_to_container(trash_vfs)

        # Agar nom takrorlansa, unikal nom yaratish
        if await self.exists(trash_vfs):
            counter = 2
            while await self.exists(f"/.Trash/{name} {counter}"):
                counter += 1
            name = f"{name} {counter}"
            trash_vfs = f"/.Trash/{name}"
            trash_container = self._vfs_to_container(trash_vfs)

        # .Trash papkasi mavjudligini ta'minlash
        await self.create_directory("/.Trash")

        source_path = self._vfs_to_container(vfs_path)
        _, exit_code = await self._exec_cmd(["mv", source_path, trash_container])
        if exit_code != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move to trash: {vfs_path}",
            )
        return trash_vfs

    async def empty_trash(self) -> int:
        """Trash papkasini tozalash. O'chirilgan fayllar sonini qaytaradi."""
        trash_path = self._vfs_to_container("/.Trash")
        # Avval nechta element borligini sanash
        items = await self.list_directory("/.Trash")
        count = len(items)
        if count > 0:
            # Trash ichidagi hamma narsani o'chirish
            _, exit_code = await self._exec_cmd(["sh", "-c", f"rm -rf {shlex.quote(trash_path)}/*"])
            if exit_code != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to empty trash",
                )
        return count

    async def read_file(self, vfs_path: str, max_size: int = 2 * 1024 * 1024) -> dict:
        """Fayl kontentini o'qish. UTF-8 matn fayllar uchun.

        Returns: {"content": str, "size": int, "encoding": "utf-8"}
        Raises: 404 (not found), 400 (directory), 413 (too large), 415 (binary)
        """
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)

        script = f"""
import json, os, sys

path = "{container_path}"
max_size = {max_size}

if not os.path.exists(path):
    print(json.dumps({{"error": "not_found"}}))
    sys.exit(0)

if os.path.isdir(path):
    print(json.dumps({{"error": "is_directory"}}))
    sys.exit(0)

size = os.path.getsize(path)
if size > max_size:
    print(json.dumps({{"error": "too_large", "size": size}}))
    sys.exit(0)

try:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    print(json.dumps({{"content": content, "size": size, "encoding": "utf-8"}}))
except UnicodeDecodeError:
    print(json.dumps({{"error": "binary_file"}}))
    sys.exit(0)
"""
        output = await self._exec_python(script)

        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.error("read_file JSON parse error: %s", output[:500])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to read file",
            ) from exc

        if "error" in data:
            err = data["error"]
            if err == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File not found: {vfs_path}",
                )
            if err == "is_directory":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Path is a directory: {vfs_path}",
                )
            if err == "too_large":
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large: {data.get('size', 0)} bytes (max {max_size})",
                )
            if err == "binary_file":
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Binary file cannot be opened as text: {vfs_path}",
                )

        return data

    async def write_file(self, vfs_path: str, content: str) -> None:
        """Fayl kontentini yozish. Fayl mavjud bo'lmasa yaratadi."""
        _validate_path(vfs_path)
        container_path = self._vfs_to_container(vfs_path)

        # Base64 orqali xavfsiz uzatish (matnda maxsus belgilar bo'lishi mumkin)
        import base64
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")

        script = f"""
import json, os, sys, base64

path = "{container_path}"
encoded = "{encoded}"

try:
    content = base64.b64decode(encoded).decode("utf-8")
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(json.dumps({{"ok": True}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
    sys.exit(1)
"""
        output = await self._exec_python(script)

        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.error("write_file JSON parse error: %s", output[:500])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to write file",
            ) from exc

        if "error" in data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Write failed: {data['error']}",
            )

    async def generate_unique_name(self, parent_vfs: str, base_name: str) -> str:
        """Papka ichida unikal nom yaratish."""
        _validate_path(parent_vfs)
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
