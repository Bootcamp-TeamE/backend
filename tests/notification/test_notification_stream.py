import asyncio
import json
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events import bus
from app.routers.notification import _notification_events
from app.services.fanout import handle_sale_created
from app.services.notification import handle_order_paid
from tests.fanout.helpers import (
    seed_category,
    seed_sale as seed_fanout_sale,
    seed_subscription,
    seed_user as seed_fanout_user,
)
from tests.conftest import auth_headers
from tests.notification.test_notification_service import _paid_order
from tests.order.helpers import seed_sale, seed_user

NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)


async def test_order_paid_wakes_user_bus(session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)

    queue = bus.subscribe(bus.USER, user.id)
    try:
        assert await handle_order_paid(session, order.id) is True
        await asyncio.wait_for(queue.get(), timeout=2)  # 유저 채널로 깨우기 신호
    finally:
        bus.unsubscribe(bus.USER, user.id, queue)


async def test_fanout_notification_in_feed(client: AsyncClient, session: AsyncSession):
    await seed_category(session)
    sale = await seed_fanout_sale(session)  # 50% 할인
    user = await seed_fanout_user(session)
    await seed_subscription(session, user_id=user.id, min_discount_rate=0)

    assert await handle_sale_created(session, sale.id, now=NOW) == 1

    # 발견 알림이 인앱 알림함에 뜬다.
    body = (await client.get("/api/v1/notifications", headers=auth_headers(user))).json()
    assert len(body) == 1
    assert body[0]["type"] == "sale_nearby"
    assert body[0]["sale_id"] == sale.id


async def test_user_stream_initial_and_update(session: AsyncSession, engine):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)
    await handle_order_paid(session, order.id)  # 알림 1건 생성

    maker = async_sessionmaker(engine, expire_on_commit=False)
    gen = _notification_events(user.id, maker)

    first = await asyncio.wait_for(gen.__anext__(), timeout=3)
    assert first.startswith("data: ")
    assert len(json.loads(first[6:])) == 1  # 결제완료 알림 1건

    await bus.publish(bus.USER, user.id)  # 구독 상태 → 갱신 프레임
    second = await asyncio.wait_for(gen.__anext__(), timeout=3)
    assert second.startswith("data: ")

    await gen.aclose()
