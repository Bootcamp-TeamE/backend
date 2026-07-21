"""점주 목데이터 적재: owner 없는 매장마다 mock 점주 1명을 만들어 연결.

실제 점주 가입 전까지 데모용. 실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/add_mock_owners.py
멱등: owner_id가 이미 있는 매장은 건너뜀.
"""

import asyncio

from sqlalchemy import func, select

import app.models  # noqa: F401
from app.database import AsyncSessionLocal, engine
from app.models.store import Store
from app.models.user import Role, User


async def main() -> None:
    async with AsyncSessionLocal() as s:
        stores = (
            await s.execute(select(Store).where(Store.owner_id.is_(None)))
        ).scalars().all()
        if not stores:
            print("owner 없는 매장 없음 — 중단.")
            return

        pairs = []
        for st in stores:
            owner = User(
                email=f"owner{st.id}@mock.local",
                google_sub=f"mock-owner-{st.id}",
                name=f"{st.name} 점주",
                role=Role.OWNER,
            )
            s.add(owner)
            pairs.append((st, owner))
        await s.flush()  # owner.id 확보
        for st, owner in pairs:
            st.owner_id = owner.id
        await s.commit()

        users = (await s.execute(select(func.count()).select_from(User))).scalar()
        null_owner = (
            await s.execute(select(func.count()).select_from(Store).where(Store.owner_id.is_(None)))
        ).scalar()
        print(f"점주 목데이터 완료 → users(점주)={users}, owner 없는 매장={null_owner}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
