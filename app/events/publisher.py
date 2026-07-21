import asyncio
import json
from functools import lru_cache
from typing import Protocol

from app.config import settings

EXCHANGE = "orders"


class EventPublisher(Protocol):
    async def publish(self, routing_key: str, payload: dict) -> None: ...


class FakePublisher:
    """테스트용 인메모리 발행기. 실제 브로커 없이 발행 이벤트를 검사한다."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, routing_key: str, payload: dict) -> None:
        self.events.append((routing_key, payload))


class RabbitMQPublisher:
    """pika 기반 발행기. blocking 호출이라 스레드로 넘겨 이벤트 루프를 막지 않는다."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def publish(self, routing_key: str, payload: dict) -> None:
        await asyncio.to_thread(self._publish_blocking, routing_key, payload)

    def _publish_blocking(self, routing_key: str, payload: dict) -> None:
        import pika

        conn = pika.BlockingConnection(pika.URLParameters(self._url))
        try:
            channel = conn.channel()
            channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            channel.basic_publish(
                exchange=EXCHANGE,
                routing_key=routing_key,
                body=json.dumps(payload).encode(),
                properties=pika.BasicProperties(delivery_mode=2),  # 메시지 durable
            )
        finally:
            conn.close()


@lru_cache
def _default_publisher() -> EventPublisher:
    return RabbitMQPublisher(settings.rabbitmq_url)


def get_publisher() -> EventPublisher:
    return _default_publisher()
