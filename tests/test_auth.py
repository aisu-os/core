import uuid
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from aiso_core.config import settings
from aiso_core.models.user import User
from aiso_core.utils.rate_limiter import get_rate_limiter
from aiso_core.utils.security import decode_token, hash_password


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
    assert response.json()["detail"] == "Only image files are accepted"


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
    assert response.json()["detail"].startswith("Allowed formats:")


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
    assert response.json()["detail"] == "File size must not exceed 2MB"


async def test_login_requires_body(client: AsyncClient):
    response = await client.post("/api/v1/auth/login")
    assert response.status_code == 422


async def test_me_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_login_success_returns_token(client: AsyncClient, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "login@example.com",
            "username": "loginuser",
            "display_name": "Login User",
            "password": "secret123",
        },
    )
    assert response.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    data = login.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]

    result = await db_session.execute(select(User).where(User.email == "login@example.com"))
    user = result.scalar_one()
    payload = decode_token(data["access_token"])
    assert payload is not None
    assert payload["sub"] == str(user.id)


async def test_login_rejects_invalid_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "wrongpass@example.com",
            "username": "wrongpassuser",
            "display_name": "Wrong Pass",
            "password": "secret123",
        },
    )
    assert response.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "badpass"},
    )
    assert login.status_code == 401
    assert login.json()["detail"] == "Invalid email or password"


async def test_login_rejects_inactive_user(client: AsyncClient, db_session):
    user = User(
        id=uuid.uuid4(),
        email="inactive@example.com",
        username="inactiveuser",
        display_name="Inactive User",
        hashed_password=hash_password("secret123"),
        avatar_url=None,
        role="user",
        is_active=False,
        cpu=settings.default_user_cpu,
        disk=settings.default_user_disk,
        wallpaper=settings.default_user_wallpaper,
    )
    db_session.add(user)
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "secret123"},
    )
    assert login.status_code == 403
    assert login.json()["detail"] == "Account is inactive"


async def test_me_success_returns_current_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "me@example.com",
            "username": "meuser",
            "display_name": "Me User",
            "password": "secret123",
        },
    )
    assert response.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "me@example.com", "password": "secret123"},
    )
    token = login.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == "me@example.com"
    assert data["username"] == "meuser"
    assert data["display_name"] == "Me User"


async def test_get_username_info_success(client: AsyncClient):
    get_rate_limiter.cache_clear()
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "usernameinfo@example.com",
            "username": "usernameinfo",
            "display_name": "Username Info",
            "password": "secret123",
        },
    )
    assert response.status_code == 201

    info = await client.get("/api/v1/auth/username-info", params={"username": "usernameinfo"})
    assert info.status_code == 200
    data = info.json()
    assert data["display_name"] == "Username Info"
    assert data["avatar_url"] is None
    assert data["wallpaper"] == settings.default_user_wallpaper


async def test_get_username_info_not_found(client: AsyncClient):
    get_rate_limiter.cache_clear()
    response = await client.get("/api/v1/auth/username-info", params={"username": "missing"})
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


async def test_get_username_info_rate_limit(client: AsyncClient):
    get_rate_limiter.cache_clear()
    response = await client.post(
        "/api/v1/auth/register",
        data={
            "email": "ratelimit@example.com",
            "username": "ratelimit",
            "display_name": "Rate Limit",
            "password": "secret123",
        },
    )
    assert response.status_code == 201

    for _ in range(settings.rate_limit_username_info_per_minute):
        ok = await client.get("/api/v1/auth/username-info", params={"username": "ratelimit"})
        assert ok.status_code == 200

    limited = await client.get("/api/v1/auth/username-info", params={"username": "ratelimit"})
    assert limited.status_code == 429
    assert limited.json()["detail"] == "Rate limit exceeded"
