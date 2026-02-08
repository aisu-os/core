from httpx import AsyncClient


async def test_register_requires_body(client: AsyncClient):
    response = await client.post("/api/v1/auth/register")
    assert response.status_code == 422


async def test_login_requires_body(client: AsyncClient):
    response = await client.post("/api/v1/auth/login")
    assert response.status_code == 422


async def test_me_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
