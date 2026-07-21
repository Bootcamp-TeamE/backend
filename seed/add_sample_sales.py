"""샘플 마감세일 적재: 매장마다 활성 세일 1건 생성(데모용).

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/add_sample_sales.py
멱등: sales가 이미 있으면 중단.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.models.category import Category
from app.models.sale import Sale, SaleStatus
from app.models.store import Store

PRICE = {
    "butcher": (25000, 15000),
    "seafood": (20000, 12000),
    "greengrocer": (10000, 6000),
    "sidedish": (8000, 4500),
    "ricecake": (12000, 7000),
    "flower": (30000, 18000),
}

TITLE = {
    "butcher": "정육 모둠",
    "seafood": "수산 모둠",
    "greengrocer": "과일·채소 모둠",
    "sidedish": "반찬 모둠",
    "ricecake": "떡 모둠",
    "flower": "꽃다발",
}


async def main() -> None:
    async with AsyncSessionLocal() as s:
        if (await s.execute(select(func.count()).select_from(Sale))).scalar():
            print("이미 세일 시드됨 — 중단.")
            return

        stores = (await s.execute(select(Store))).scalars().all()
        default_units = {c.code: c.default_unit_code for c in (await s.execute(select(Category))).scalars().all()}
        now = datetime.now(timezone.utc)
        for st in stores:
            normal_price, sale_price = PRICE.get(st.category_code, (10000, 6000))
            quantity = 5 + st.id % 8
            s.add(Sale(
                store_id=st.id, category_code=st.category_code,
                title=TITLE.get(st.category_code, "마감 특가"), normal_price=normal_price, sale_price=sale_price,
                unit_code=default_units[st.category_code], min_order=1,
                total_quantity=quantity, remaining_quantity=quantity,
                deadline_at=now + timedelta(hours=2 + st.id % 6), status=SaleStatus.ACTIVE,
            ))
        await s.commit()
        total = (await s.execute(select(func.count()).select_from(Sale))).scalar()
        print(f"샘플 세일 {total}건 생성")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
