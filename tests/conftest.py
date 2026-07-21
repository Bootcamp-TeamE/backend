import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.config import settings
from app.database import Base, get_session
from app.main import app


async def _ensure_test_database() -> None:
    test_db = settings.test_database_url.rsplit("/", 1)[-1]
    admin = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = (
            await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": test_db}
            )
        ).scalar()
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    await admin.dispose()


@pytest_asyncio.fixture
async def engine():
    await _ensure_test_database()
    eng = create_async_engine(settings.test_database_url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def client(engine) -> AsyncClient:
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
