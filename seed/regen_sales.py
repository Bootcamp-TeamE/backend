"""세일 완전 초기화 후 재생성(데모용, 되돌릴 수 없음).

세일과 이를 참조하는 주문·알림을 모두 비운 뒤, 지역 비율(서울 20%·시흥 40%)로
매장을 뽑아 매장당 2~5개의 세일을 새로 만든다.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/regen_sales.py
전제: postgis 컨테이너 기동 + load_seed 완료, .env 유효.
"""

import asyncio
import random

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.services.sale_generator import generate_sales, purge_sales


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await purge_sales(session)
        created = await generate_sales(session, random.Random())
        print(f"완전 초기화 후 세일 {created}건 생성")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
