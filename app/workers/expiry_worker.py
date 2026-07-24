"""예약·픽업 만료를 주기 실행하는 보장 계층 워커.

- 예약(reserved) 만료시각 경과 → expired + 재고 원복
- 결제(paid) 픽업 데드라인 경과 → refunded(no-show) + (마감 전이면)재고 원복 + 환불 알림

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python -m app.workers.expiry_worker
전제: postgis + redis 컨테이너 기동, .env 유효.
"""

import asyncio
import logging

from app.database import AsyncSessionLocal, engine
from app.services.notification import handle_order_refunded
from app.services.order import sweep_expired_orders, sweep_pickup_expired_orders

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60


async def _tick() -> None:
    async with AsyncSessionLocal() as session:
        expired = await sweep_expired_orders(session)
        refunded = await sweep_pickup_expired_orders(session)

    if expired:
        logger.info("예약 만료 %s건", expired)
    # 환불 알림은 개별 세션에서(멱등 upsert + SSE push). 실패해도 환불 자체는 커밋됨.
    for order_id in refunded:
        async with AsyncSessionLocal() as session:
            await handle_order_refunded(session, order_id)
    if refunded:
        logger.info("픽업 만료 환불 %s건", len(refunded))


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("만료 워커 시작 — %s초 주기", SWEEP_INTERVAL_SECONDS)
    try:
        while True:
            try:
                await _tick()
            except Exception:
                logger.exception("만료 스윕 실패")
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
