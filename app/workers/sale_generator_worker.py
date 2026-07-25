"""마감세일 생성·재생성 워커.

하루 종일 2시간 간격(정각, 짝수 시 00·02·…·22시, KST)으로 run_cycle 실행:
- 세일이 없으면 초기 생성(지역 비율 서울 20%·시흥 40%, 매장당 2~5개)
- 있으면 마감이 지난 세일의 가격·할인·마감시각을 재생성해 되살림

기동 직후에도 1회 실행해 배포/재시작 후 데이터가 비어 있지 않게 한다.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python -m app.workers.sale_generator_worker
전제: postgis 컨테이너 기동 + 시드(load_seed) 완료, .env 유효.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.database import AsyncSessionLocal, engine
from app.services.sale_generator import run_cycle

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
SLOTS = list(range(0, 24, 2))  # 하루 종일 2시간 간격(정각, 짝수 시). 12시 포함.


def next_slot(now: datetime) -> datetime:
    """now 이후 가장 가까운 실행 시각(오늘 남은 슬롯, 없으면 내일 첫 슬롯)."""
    today = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in SLOTS]
    future = [t for t in today if t > now]
    if future:
        return min(future)
    return today[0] + timedelta(days=1)


async def _tick() -> None:
    async with AsyncSessionLocal() as session:
        result = await run_cycle(session)
    if result["created"]:
        logger.info("세일 초기 생성 %s건", result["created"])
    if result["refreshed"]:
        logger.info("마감 세일 재생성 %s건", result["refreshed"])


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("세일 생성 워커 시작 — %s시 KST 2시간 간격", SLOTS)
    try:
        await _tick()  # 기동 직후 1회(데이터 보장)
        while True:
            target = next_slot(datetime.now(KST))
            await asyncio.sleep(max(0, (target - datetime.now(KST)).total_seconds()))
            try:
                await _tick()
            except Exception:
                logger.exception("세일 생성 사이클 실패")
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
