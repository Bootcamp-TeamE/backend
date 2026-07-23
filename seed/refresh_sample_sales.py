"""데모용 마감세일 '다시 열기': deadline_at을 미래로, 재고·상태 초기화.

add_sample_sales.py는 최초 1회 생성용(멱등). 세일은 시간이 지나면 마감되어 검색에서
빠지므로, 데모/개발 때마다 이 스크립트로 마감시각을 미래로 갱신해 세일을 되살린다.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/refresh_sample_sales.py
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select, update

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.models.sale import Sale, SaleStatus


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # id로 1~8시간 분산 → 마감 임박/여유가 섞이게. 한 번의 벌크 UPDATE.
        await s.execute(
            update(Sale).values(
                deadline_at=func.now() + func.make_interval(0, 0, 0, 0, (Sale.id % 8) + 1),
                remaining_quantity=Sale.total_quantity,
                status=SaleStatus.ACTIVE,
            )
        )
        await s.commit()

        now = datetime.now(timezone.utc)
        total = (await s.execute(select(func.count()).select_from(Sale))).scalar()
        future = (
            await s.execute(
                select(func.count()).select_from(Sale).where(Sale.deadline_at > now)
            )
        ).scalar()
        print(f"세일 {total}건 갱신 → 마감 전 {future}건 (1~8시간 후 마감)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
