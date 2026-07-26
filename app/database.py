from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """세션 팩토리 자체를 주입. SSE처럼 요청 세션을 오래 붙잡으면 안 되는 곳에서
    스냅샷마다 짧은 세션을 열고 닫기 위해 사용(테스트에서 오버라이드 가능)."""
    return AsyncSessionLocal
