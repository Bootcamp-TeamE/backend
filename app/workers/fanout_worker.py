"""sale.created 이벤트를 소비해 조건 매칭 유저에게 fanout 알림을 발송하는 워커.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python -m app.workers.fanout_worker
전제: postgis + rabbitmq 컨테이너 기동, .env 유효.
"""

import asyncio
import json
import logging

import pika

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.events.publisher import EXCHANGE
from app.services.fanout import handle_sale_created

logger = logging.getLogger(__name__)

QUEUE = "fanout.sale_created"
ROUTING_KEY = "sale.created"


async def _handle(sale_id: int) -> None:
    async with AsyncSessionLocal() as session:
        sent = await handle_sale_created(session, sale_id)
        logger.info("fanout 발송 sale_id=%s → %s건", sale_id, sent)


def _on_message(channel, method, _properties, body: bytes) -> None:
    try:
        sale_id = json.loads(body)["sale_id"]
        asyncio.run(_handle(sale_id))
        channel.basic_ack(method.delivery_tag)
    except Exception:
        logger.exception("sale.created 처리 실패 body=%s", body)
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

    logger.info("fanout 워커 시작 — %s 대기", QUEUE)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        conn.close()
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
