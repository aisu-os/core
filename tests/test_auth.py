from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from aiso_core.config import settings
from aiso_core.models.user import User


async def test_register_requires_body(client: AsyncClient):
    response = await client.post("/api/v1/auth/register")
    assert response.status_code == 422


async def test_register_success(client: AsyncClient, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "user@example.com",
            "username": "user1",
            "display_name": "User One",
            "password": "secret123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "user1"
    assert data["display_name"] == "User One"
    assert data["avatar_url"] is None
    assert data["wallpaper"] == settings.default_user_wallpaper

    result = await db_session.execute(select(User).where(User.email == "user@example.com"))
    user = result.scalar_one()
    assert user.username == "user1"
    assert user.display_name == "User One"
    assert user.hashed_password != "secret123"
    assert user.avatar_url is None


async def test_register_rejects_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "not-an-email",
            "username": "user2",
            "display_name": "User Two",
            "password": "secret123",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid email format"


async def test_register_rejects_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dupe@example.com",
        "username": "user3",
        "display_name": "User Three",
        "password": "secret123",
    }
    first = await client.post("/api/v1/auth/register", data=payload)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "dupe@example.com",
            "username": "user4",
            "display_name": "User Four",
            "password": "secret123",
        },
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "This email is already registered"


async def test_register_rejects_duplicate_username(client: AsyncClient):
    payload = {
        "email": "unique@example.com",
        "username": "dupeuser",
        "display_name": "User Five",
        "password": "secret123",
    }
    first = await client.post("/api/v1/auth/register", data=payload)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "unique2@example.com",
            "username": "dupeuser",
            "display_name": "User Six",
            "password": "secret123",
        },
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "This username is already taken"


async def test_register_avatar_upload_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "avatar@example.com",
            "username": "avataruser",
            "display_name": "Avatar User",
            "password": "secret123",
        },
        files={"avatar": ("avatar.png", b"fakepngdata", "image/png")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["avatar_url"] is not None
    assert data["avatar_url"].startswith(settings.app_url)
    assert "/uploads/avatars/" in data["avatar_url"]

    avatars_dir = Path(settings.upload_dir) / "avatars"
    assert avatars_dir.exists()
    assert any(avatars_dir.iterdir())


async def test_register_avatar_emoji_url(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "emoji@example.com",
            "username": "emojiuser",
            "display_name": "Emoji User",
            "password": "secret123",
            "avatar_emoji": "https://example.com/emoji.png",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["avatar_url"] == "https://example.com/emoji.png"


async def test_register_rejects_non_image_avatar(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "badfile@example.com",
            "username": "badfileuser",
            "display_name": "Bad File",
            "password": "secret123",
        },
        files={"avatar": ("avatar.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Faqat rasm fayllari qabul qilinadi"


async def test_register_rejects_avatar_extension(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "badext@example.com",
            "username": "badextuser",
            "display_name": "Bad Ext",
            "password": "secret123",
        },
        files={"avatar": ("avatar.txt", b"fakepngdata", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Ruxsat berilgan formatlar:")


async def test_register_rejects_avatar_too_large(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "large@example.com",
            "username": "largeuser",
            "display_name": "Large File",
            "password": "secret123",
        },
        files={"avatar": ("avatar.png", b"a" * (2 * 1024 * 1024 + 1), "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Fayl hajmi 2MB dan oshmasligi kerak"


async def test_login_requires_body(client: AsyncClient):
    response = await client.post("/api/v1/auth/login")
    assert response.status_code == 422


async def test_me_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
