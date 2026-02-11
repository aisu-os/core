from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str, username: str) -> str:
    register = await client.post(
        "/api/v1/auth/register",
        data={
            "email": email,
            "username": username,
            "display_name": username,
            "password": "secret123",
        },
    )
    assert register.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "secret123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_fs_tree_seeds_default_dirs(client: AsyncClient):
    token = await _register_and_login(client, "fs1@example.com", "fsuser1")

    tree = await client.get("/api/v1/fs/tree", headers=_auth_headers(token))
    assert tree.status_code == 200
    data = tree.json()
    assert data["path"] == "/"

    child_names = {child["name"] for child in data["children"]}
    expected = {
        "Desktop",
        "Documents",
        "Downloads",
        "Pictures",
        "Music",
        "Videos",
        ".Trash",
    }
    assert child_names == expected


async def test_fs_list_directory_and_get_node(client: AsyncClient):
    token = await _register_and_login(client, "fs2@example.com", "fsuser2")

    root = await client.get(
        "/api/v1/fs/ls",
        params={"path": "/"},
        headers=_auth_headers(token),
    )
    assert root.status_code == 200
    root_data = root.json()
    assert root_data["path"] == "/"
    assert root_data["total"] == 7

    created = await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Documents",
            "name": "note.txt",
            "node_type": "file",
            "size": 12,
        },
        headers=_auth_headers(token),
    )
    assert created.status_code == 201
    created_data = created.json()
    assert created_data["path"] == "/Documents/note.txt"
    assert created_data["node_type"] == "file"

    fetched = await client.get(
        "/api/v1/fs/node",
        params={"path": "/Documents/note.txt"},
        headers=_auth_headers(token),
    )
    assert fetched.status_code == 200
    assert fetched.json()["path"] == "/Documents/note.txt"


async def test_fs_rename_and_move(client: AsyncClient):
    token = await _register_and_login(client, "fs3@example.com", "fsuser3")

    await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Documents",
            "name": "note.txt",
            "node_type": "file",
            "size": 5,
        },
        headers=_auth_headers(token),
    )

    renamed = await client.patch(
        "/api/v1/fs/rename",
        json={"path": "/Documents/note.txt", "new_name": "note2.txt"},
        headers=_auth_headers(token),
    )
    assert renamed.status_code == 200
    renamed_data = renamed.json()
    assert renamed_data["old_path"] == "/Documents/note.txt"
    assert renamed_data["new_path"] == "/Documents/note2.txt"

    moved = await client.post(
        "/api/v1/fs/move",
        json={"source_path": "/Documents/note2.txt", "dest_parent_path": "/Downloads"},
        headers=_auth_headers(token),
    )
    assert moved.status_code == 200
    moved_data = moved.json()
    assert moved_data["new_path"] == "/Downloads/note2.txt"


async def test_fs_copy_and_search(client: AsyncClient):
    token = await _register_and_login(client, "fs4@example.com", "fsuser4")

    await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Documents",
            "name": "Projects",
            "node_type": "directory",
        },
        headers=_auth_headers(token),
    )
    await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Documents/Projects",
            "name": "readme.txt",
            "node_type": "file",
            "size": 3,
        },
        headers=_auth_headers(token),
    )

    copied = await client.post(
        "/api/v1/fs/copy",
        json={"source_path": "/Documents/Projects", "dest_parent_path": "/Desktop"},
        headers=_auth_headers(token),
    )
    assert copied.status_code == 200
    new_root = copied.json()["new_path"]
    assert new_root == "/Desktop/Projects"

    copied_file = await client.get(
        "/api/v1/fs/node",
        params={"path": f"{new_root}/readme.txt"},
        headers=_auth_headers(token),
    )
    assert copied_file.status_code == 200

    search = await client.get(
        "/api/v1/fs/search",
        params={"q": "Projects"},
        headers=_auth_headers(token),
    )
    assert search.status_code == 200
    paths = {item["path"] for item in search.json()}
    assert "/Documents/Projects" in paths
    assert new_root in paths


async def test_fs_delete_restore_and_empty_trash(client: AsyncClient):
    token = await _register_and_login(client, "fs5@example.com", "fsuser5")

    await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Documents",
            "name": "temp.txt",
            "node_type": "file",
        },
        headers=_auth_headers(token),
    )

    deleted = await client.post(
        "/api/v1/fs/delete",
        json={"path": "/Documents/temp.txt", "permanent": False},
        headers=_auth_headers(token),
    )
    assert deleted.status_code == 200
    trashed_path = deleted.json()["path"]
    assert trashed_path.startswith("/.Trash/")

    trash = await client.get("/api/v1/fs/trash", headers=_auth_headers(token))
    assert trash.status_code == 200
    trash_paths = {item["path"] for item in trash.json()}
    assert trashed_path in trash_paths

    restored = await client.post(
        "/api/v1/fs/restore",
        json={"path": trashed_path},
        headers=_auth_headers(token),
    )
    assert restored.status_code == 200
    assert restored.json()["new_path"] == "/Documents/temp.txt"

    trash_after_restore = await client.get("/api/v1/fs/trash", headers=_auth_headers(token))
    assert trash_after_restore.status_code == 200
    assert trash_after_restore.json() == []

    await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Documents",
            "name": "junk.txt",
            "node_type": "file",
        },
        headers=_auth_headers(token),
    )
    await client.post(
        "/api/v1/fs/delete",
        json={"path": "/Documents/junk.txt", "permanent": False},
        headers=_auth_headers(token),
    )

    emptied = await client.post("/api/v1/fs/empty-trash", headers=_auth_headers(token))
    assert emptied.status_code == 200
    assert emptied.json()["deleted"] >= 1

    trash_after_empty = await client.get("/api/v1/fs/trash", headers=_auth_headers(token))
    assert trash_after_empty.status_code == 200
    assert trash_after_empty.json() == []


async def test_fs_bulk_move_and_bulk_delete(client: AsyncClient):
    token = await _register_and_login(client, "fs6@example.com", "fsuser6")

    for name in ["a.txt", "b.txt"]:
        created = await client.post(
            "/api/v1/fs/node",
            json={
                "parent_path": "/Documents",
                "name": name,
                "node_type": "file",
            },
            headers=_auth_headers(token),
        )
        assert created.status_code == 201

    moved = await client.post(
        "/api/v1/fs/bulk-move",
        json={
            "source_paths": ["/Documents/a.txt", "/Documents/b.txt"],
            "dest_parent_path": "/Downloads",
        },
        headers=_auth_headers(token),
    )
    assert moved.status_code == 200
    moved_data = moved.json()
    assert set(moved_data["succeeded"]) == {"/Documents/a.txt", "/Documents/b.txt"}
    assert moved_data["failed"] == []

    downloads = await client.get(
        "/api/v1/fs/ls",
        params={"path": "/Downloads"},
        headers=_auth_headers(token),
    )
    assert downloads.status_code == 200
    download_names = {child["name"] for child in downloads.json()["children"]}
    assert {"a.txt", "b.txt"}.issubset(download_names)

    bulk_deleted = await client.post(
        "/api/v1/fs/bulk-delete",
        json={
            "paths": ["/Downloads/a.txt", "/Downloads/missing.txt"],
            "permanent": True,
        },
        headers=_auth_headers(token),
    )
    assert bulk_deleted.status_code == 200
    deleted_data = bulk_deleted.json()
    assert "/Downloads/a.txt" in deleted_data["succeeded"]
    assert deleted_data["failed"] == [
        {"path": "/Downloads/missing.txt", "error": "Node not found: /Downloads/missing.txt"}
    ]

    missing = await client.get(
        "/api/v1/fs/node",
        params={"path": "/Downloads/a.txt"},
        headers=_auth_headers(token),
    )
    assert missing.status_code == 404


async def test_fs_update_desktop_positions(client: AsyncClient):
    token = await _register_and_login(client, "fs7@example.com", "fsuser7")

    created_one = await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Desktop",
            "name": "alpha.txt",
            "node_type": "file",
        },
        headers=_auth_headers(token),
    )
    assert created_one.status_code == 201

    created_two = await client.post(
        "/api/v1/fs/node",
        json={
            "parent_path": "/Desktop",
            "name": "beta.txt",
            "node_type": "file",
        },
        headers=_auth_headers(token),
    )
    assert created_two.status_code == 201

    updated = await client.patch(
        "/api/v1/fs/desktop-positions",
        json={
            "positions": [
                {"path": "/Desktop/alpha.txt", "x": 120, "y": 240},
                {"path": "/Desktop/beta.txt", "x": 12, "y": 34},
            ]
        },
        headers=_auth_headers(token),
    )
    assert updated.status_code == 200
    updated_data = updated.json()
    assert len(updated_data) == 2
    positions = {item["path"]: (item["desktop_x"], item["desktop_y"]) for item in updated_data}
    assert positions["/Desktop/alpha.txt"] == (120, 240)
    assert positions["/Desktop/beta.txt"] == (12, 34)

    alpha = await client.get(
        "/api/v1/fs/node",
        params={"path": "/Desktop/alpha.txt"},
        headers=_auth_headers(token),
    )
    assert alpha.status_code == 200
    assert (alpha.json()["desktop_x"], alpha.json()["desktop_y"]) == (120, 240)
