"""주문 이벤트를 소비해 개인 알림을 발송하는 워커 프로세스.

order.paid → 결제 완료 알림, order.picked_up → 픽업 완료 알림.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python -m app.workers.notification_worker
전제: postgis + rabbitmq 컨테이너 기동, .env 유효.
"""

import asyncio
import json
import logging

import pika

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.events.publisher import EXCHANGE
from app.services.notification import handle_order_paid, handle_order_picked_up

logger = logging.getLogger(__name__)

# (큐, 라우팅 키, 핸들러)
BINDINGS = [
    ("notification.order_paid", "order.paid", handle_order_paid),
    ("notification.order_picked_up", "order.picked_up", handle_order_picked_up),
]
_HANDLERS = {routing_key: handler for _, routing_key, handler in BINDINGS}


async def _handle(handler, order_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await handler(session, order_id)


def _on_message(channel, method, _properties, body: bytes) -> None:
    try:
        order_id = json.loads(body)["order_id"]
        handler = _HANDLERS[method.routing_key]
        asyncio.run(_handle(handler, order_id))
        channel.basic_ack(method.delivery_tag)
    except Exception:
        logger.exception("알림 처리 실패 key=%s body=%s", method.routing_key, body)
        # requeue=False: 포이즌 메시지 무한 재처리 방지. DLQ 연결은 신뢰성 단계에서.
        channel.basic_nack(method.delivery_tag, requeue=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = conn.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    for queue, routing_key, _ in BINDINGS:
        channel.queue_declare(queue=queue, durable=True)
        channel.queue_bind(exchange=EXCHANGE, queue=queue, routing_key=routing_key)
        channel.basic_consume(queue=queue, on_message_callback=_on_message)
    channel.basic_qos(prefetch_count=10)

    logger.info("알림 워커 시작 — order.paid / order.picked_up 대기")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        conn.close()
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
