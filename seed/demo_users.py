"""데모 유저 시드 — 구매자 1명 + 점주 1명(첫 매장에 귀속). 멱등.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/demo_users.py
"""

import asyncio

from sqlalchemy import select

import app.models  # noqa: F401
from app.database import AsyncSessionLocal, engine
from app.models.store import Store
from app.models.user import Role, User

DEMO_BUYER = ("buyer@solde.demo", "데모구매자")
DEMO_OWNER = ("owner@solde.demo", "데모점주")


async def _upsert(session, email, name, role) -> User:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, google_sub=f"demo:{email}", name=name, role=role)
        session.add(user)
        await session.flush()
    return user


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await _upsert(session, *DEMO_BUYER, Role.USER)
        owner = await _upsert(session, *DEMO_OWNER, Role.OWNER)
        # 주인 없는 첫 매장을 데모 점주에게 귀속(이미 있으면 유지).
        has_store = (
            await session.execute(select(Store).where(Store.owner_id == owner.id))
        ).scalar_one_or_none()
        if has_store is None:
            free = (
                await session.execute(
                    select(Store).where(Store.owner_id.is_(None), Store.is_deleted.is_(False)).limit(1)
                )
            ).scalar_one_or_none()
            if free is not None:
                free.owner_id = owner.id
        await session.commit()
        print(f"데모 유저 시드 완료: {DEMO_BUYER[0]}, {DEMO_OWNER[0]}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
