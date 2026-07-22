from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.fanout as fanout
from app.models.notification_log import NotificationLog
from app.services.fanout import handle_sale_created
from tests.fanout.helpers import seed_category, seed_sale, seed_subscription, seed_user

NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)  # 오전 10시 고정


async def _log_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(NotificationLog))).scalar()


async def test_fanout_sends_to_matching_subscription(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session, normal_price=10000, sale_price=5000)  # 50% 할인
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, min_discount_rate=30)

    sent = await handle_sale_created(session, sale.id, now=NOW)
    assert sent == 1
    assert await _log_count(session) == 1


async def test_fanout_skips_category_mismatch(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session, category="butcher")
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, categories=["seafood"])

    assert await handle_sale_created(session, sale.id, now=NOW) == 0


async def test_fanout_skips_discount_below_min(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session, normal_price=10000, sale_price=8000)  # 20% 할인
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, min_discount_rate=50)

    assert await handle_sale_created(session, sale.id, now=NOW) == 0


async def test_fanout_skips_price_above_max(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session, sale_price=5000)
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, max_price=4000)

    assert await handle_sale_created(session, sale.id, now=NOW) == 0


async def test_fanout_skips_out_of_radius(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session, lat=37.58, lng=127.04)
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, lat=35.1, lng=129.0, radius_m=2000)  # 부산

    assert await handle_sale_created(session, sale.id, now=NOW) == 0


async def test_fanout_skips_opted_out_and_push_disabled(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session)
    u1 = await seed_user(session, i=1)
    u2 = await seed_user(session, i=2)
    await seed_subscription(session, user_id=u1.id, opted_out=True)
    await seed_subscription(session, user_id=u2.id, push_enabled=False)

    assert await handle_sale_created(session, sale.id, now=NOW) == 0


async def test_fanout_skips_outside_receive_window(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session)
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, receive_from=20, receive_to=23)

    assert await handle_sale_created(session, sale.id, now=NOW) == 0  # NOW=10시


async def test_fanout_idempotent_on_redelivery(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session)
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id)

    assert await handle_sale_created(session, sale.id, now=NOW) == 1
    assert await handle_sale_created(session, sale.id, now=NOW) == 0  # 중복 이벤트 → 재발송 없음
    assert await _log_count(session) == 1


async def test_fanout_dedupes_multiple_subscriptions_of_same_user(client, session: AsyncSession):
    await seed_category(session)
    sale = await seed_sale(session)
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id, categories=["butcher"])
    await seed_subscription(session, user_id=user.id, categories=["butcher"], radius_m=5000)

    assert await handle_sale_created(session, sale.id, now=NOW) == 1  # 유저당 1건
    assert await _log_count(session) == 1


async def test_fanout_respects_daily_quota(client, session: AsyncSession, monkeypatch):
    monkeypatch.setattr(fanout, "DAILY_QUOTA", 1)
    await seed_category(session)
    user = await seed_user(session)
    await seed_subscription(session, user_id=user.id)

    # 쿼터는 created_at(서버 시각) 기준 '오늘' 발송 수 → now도 서버와 같은 실제 시각으로.
    now = datetime.now(timezone.utc)
    first = await seed_sale(session)
    assert await handle_sale_created(session, first.id, now=now) == 1  # 1건(쿼터 소진)

    second = await seed_sale(session)
    assert await handle_sale_created(session, second.id, now=now) == 0  # 쿼터 초과 → 발송 안 함
