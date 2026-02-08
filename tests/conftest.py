from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from aiso_core.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
