"""주문 만료 즉시 계층 — Redis TTL 키 arm/disarm.

예약/결제 시 만료 시각에 맞춰 TTL 키를 걸어두면(expiry_listener가 만료 이벤트를 소비),
데드라인 정각에 즉시 만료·환불된다. 모두 best-effort — 실패해도 보장 계층(sweep)이 처리한다.
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


def _client() -> aioredis.Redis:
    # 요청 경로에서 호출되므로 Redis 지연/장애가 응답을 막지 않게 짧은 타임아웃.
    return aioredis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)


async def arm(key: str, ttl_seconds: int) -> None:
    """key를 ttl_seconds 후 만료되게 SET. 만료 이벤트를 리스너가 받아 즉시 처리한다."""
    try:
        client = _client()
        try:
            await client.set(key, "1", ex=max(1, ttl_seconds))
        finally:
            await client.aclose()
    except Exception:
        logger.warning("만료 TTL arm 실패 key=%s (sweep가 보장)", key)


async def disarm(*keys: str) -> None:
    """상태가 바뀌어 더 이상 만료 대상이 아닌 키를 제거(불필요한 만료 이벤트 방지)."""
    if not keys:
        return
    try:
        client = _client()
        try:
            await client.delete(*keys)
        finally:
            await client.aclose()
    except Exception:
        logger.warning("만료 TTL disarm 실패 keys=%s", keys)
