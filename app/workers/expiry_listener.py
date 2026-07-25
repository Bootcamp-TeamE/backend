"""주문 만료 즉시 계층 워커 — Redis 키 만료 이벤트를 소비해 데드라인 정각에 처리한다.

- 예약 홀드(5분)/픽업 데드라인(30분) TTL 키가 만료되면 그 즉시 expire/refund.
- 보장 계층(expiry_worker의 주기 sweep)과 멱등 코어(expire_order/refund_order)를 공유 →
  중복 실행돼도 안전. Redis 재시작 등으로 이벤트가 유실되면 sweep가 뒤늦게라도 처리한다.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python -m app.workers.expiry_listener
전제: postgis + redis 컨테이너 기동, .env 유효.
"""

import asyncio
import logging

import redis.asyncio as aioredis

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.services.notification import handle_order_refunded
from app.services.order import EXPIRE_KEY_PREFIX, PICKUP_KEY_PREFIX, handle_expired_key

logger = logging.getLogger(__name__)

PATTERN = "__keyevent@*__:expired"  # 모든 db의 키 만료 이벤트


async def _on_expired(key: str) -> None:
    if not (key.startswith(EXPIRE_KEY_PREFIX) or key.startswith(PICKUP_KEY_PREFIX)):
        return  # 우리 키가 아님
    async with AsyncSessionLocal() as session:
        result = await handle_expired_key(session, key)
    if result is None:
        return
    kind, order_id = result
    if kind == "refunded":
        # 환불 알림은 개별 세션에서(멱등 upsert + SSE push).
        async with AsyncSessionLocal() as session:
            await handle_order_refunded(session, order_id)
    logger.info("즉시 %s order_id=%s", "환불" if kind == "refunded" else "만료", order_id)


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    client = aioredis.from_url(settings.redis_url)
    # 키 만료 이벤트 발행 활성화(E=keyevent, x=expired). 런타임 설정.
    await client.config_set("notify-keyspace-events", "Ex")
    pubsub = client.pubsub()
    await pubsub.psubscribe(PATTERN)
    logger.info("만료 리스너 시작 — %s 대기", PATTERN)
    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            data = message["data"]
            key = data.decode() if isinstance(data, (bytes, bytearray)) else str(data)
            try:
                await _on_expired(key)
            except Exception:
                logger.exception("만료 키 처리 실패 key=%s", key)
    finally:
        await pubsub.aclose()
        await client.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
