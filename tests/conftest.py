from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from aiso_core.config import settings
from aiso_core.database import get_db
from aiso_core.main import app
from aiso_core.models.user import User
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
async def client(
    async_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> AsyncGenerator[AsyncClient, None]:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(settings, "app_url", "http://testserver")
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    get_rate_limiter.cache_clear()

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
