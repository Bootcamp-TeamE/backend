"""order.paid 이벤트를 소비해 결제 완료 알림을 발송하는 워커 프로세스.

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
from app.services.notification import handle_order_paid

logger = logging.getLogger(__name__)

QUEUE = "notification.order_paid"
ROUTING_KEY = "order.paid"


async def _handle(order_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await handle_order_paid(session, order_id)


def _on_message(channel, method, _properties, body: bytes) -> None:
    try:
        order_id = json.loads(body)["order_id"]
        asyncio.run(_handle(order_id))
        channel.basic_ack(method.delivery_tag)
    except Exception:
        logger.exception("order.paid 처리 실패 body=%s", body)
        # requeue=False: 포이즌 메시지 무한 재처리 방지. DLQ 연결은 신뢰성 단계에서.
        channel.basic_nack(method.delivery_tag, requeue=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    conn = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = conn.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.queue_bind(exchange=EXCHANGE, queue=QUEUE, routing_key=ROUTING_KEY)
    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=QUEUE, on_message_callback=_on_message)

    logger.info("알림 워커 시작 — %s 대기", QUEUE)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        conn.close()
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
