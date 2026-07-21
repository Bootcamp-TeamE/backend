"""공공데이터 시드를 Postgres에 적재한다.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/load_seed.py
전제: postgis 컨테이너 기동 + .env DATABASE_URL 유효.
멱등: 이미 markets가 있으면 중단.
"""

import asyncio
import csv
from pathlib import Path

from sqlalchemy import func, select

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.models.category import Category
from app.models.market import Market
from app.models.store import Store

SEED_DIR = Path(__file__).parent

CATEGORIES = [
    ("butcher", "정육", 1), ("seafood", "수산", 2), ("greengrocer", "청과", 3),
    ("sidedish", "반찬", 4), ("ricecake", "떡", 5), ("tofu_namul", "두부·나물", 6),
    ("egg_dairy", "계란·유제품", 7), ("streetfood", "시장먹거리", 8), ("flower", "화훼", 9),
]


async def main() -> None:
    # 스키마는 Alembic이 담당.
    async with AsyncSessionLocal() as s:
        if (await s.execute(select(func.count()).select_from(Market))).scalar():
            print("이미 시드됨 — 중단(중복 방지). 다시 넣으려면 DB를 비우세요.")
            return

        for code, name_ko, order in CATEGORIES:
            s.add(Category(code=code, name_ko=name_ko, sort_order=order))
        await s.flush()

        mid_to_market: dict[str, Market] = {}
        with open(SEED_DIR / "markets_seed.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                m = Market(
                    name=r["name"], market_type=r["type"], address=r["address"],
                    lat=float(r["lat"]), lng=float(r["lng"]),
                )
                s.add(m)
                mid_to_market[r["mid"]] = m
        await s.flush()  # market.id 확보

        with open(SEED_DIR / "stores_seed.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                m = mid_to_market.get(r["market_id"])
                s.add(Store(
                    name=r["name"], category_code=r["category_code"],
                    market_id=m.id if m else None, owner_id=None,
                    address=r["address"], lat=float(r["lat"]), lng=float(r["lng"]),
                ))
        await s.commit()

        async def count(model) -> int:
            return (await s.execute(select(func.count()).select_from(model))).scalar()

        print("시드 완료 →",
              f"categories={await count(Category)}",
              f"markets={await count(Market)}",
              f"stores={await count(Store)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
