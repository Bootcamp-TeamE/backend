"""SSE 스트림 깨우기 버스. 프로세스 내 + Redis pub/sub로 프로세스 간 전달.

- 같은 프로세스(앱 내 이벤트)는 로컬 큐로 즉시 전달.
- 다른 프로세스(별도 워커 → 앱)는 Redis pub/sub으로 전달(워커가 만든 알림을 앱 SSE로).
- 신호는 데이터를 싣지 않는다(깨우기용). 유실돼도 스냅샷 재조회로 수렴(best-effort).
- origin 토큰으로 자기 프로세스 발행은 리스너에서 건너뛴다(로컬 전달과 중복 방지).
"""

import asyncio
import logging
import uuid
from collections import defaultdict

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

DASHBOARD = "dashboard"
USER = "user"
_TOPIC = "sse-bus"
_ORIGIN = uuid.uuid4().hex  # 이 프로세스 식별자

_subscribers: dict[tuple[str, int], set[asyncio.Queue]] = defaultdict(set)


def subscribe(channel: str, key: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers[(channel, key)].add(queue)
    return queue


def unsubscribe(channel: str, key: int, queue: asyncio.Queue) -> None:
    subs = _subscribers.get((channel, key))
    if subs is None:
        return
    subs.discard(queue)
    if not subs:
        _subscribers.pop((channel, key), None)


def _deliver_local(channel: str, key: int) -> None:
    for queue in _subscribers.get((channel, key), ()):
        queue.put_nowait(None)  # 깨우기 신호(데이터 없음)


async def publish(channel: str, key: int) -> None:
    _deliver_local(channel, key)  # 같은 프로세스 구독자에 즉시 전달
    try:  # 다른 프로세스(워커→앱)로 전달, best-effort
        client = aioredis.from_url(settings.redis_url)
        try:
            await client.publish(_TOPIC, f"{_ORIGIN}:{channel}:{key}")
        finally:
            await client.aclose()
    except Exception:
        logger.exception("SSE 버스 Redis 발행 실패 channel=%s key=%s", channel, key)


async def listen() -> None:
    """앱 프로세스에서 백그라운드로 실행. 다른 프로세스의 발행을 로컬 큐로 전달."""
    try:
        client = aioredis.from_url(settings.redis_url)
        pubsub = client.pubsub()
        await pubsub.subscribe(_TOPIC)
        logger.info("SSE 버스 리스너 시작")
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            origin, channel, key = message["data"].decode().split(":")
            if origin == _ORIGIN:
                continue  # 자기 프로세스 발행은 이미 로컬 전달함
            _deliver_local(channel, int(key))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("SSE 버스 리스너 종료(예외)")
