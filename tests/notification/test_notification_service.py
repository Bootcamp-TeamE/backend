from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.order import Order, OrderStatus
from app.services.notification import handle_order_paid, handle_order_refunded
from tests.order.helpers import seed_sale, seed_user


async def _paid_order(session: AsyncSession, user, sale) -> Order:
    now = datetime.now(timezone.utc)
    order = Order(
        user_id=user.id,
        sale_id=sale.id,
        quantity=1,
        total_price=sale.sale_price,
        status=OrderStatus.PAID,
        reserved_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def test_handle_order_refunded_creates_notification(session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)

    assert await handle_order_refunded(session, order.id) is True

    rows = (
        await session.execute(select(Notification).where(Notification.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].type == NotificationType.ORDER_REFUNDED
    assert rows[0].order_id == order.id


async def test_handle_order_paid_creates_notification(session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)

    assert await handle_order_paid(session, order.id) is True

    rows = (
        await session.execute(select(Notification).where(Notification.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].type == NotificationType.ORDER_PAID
    assert rows[0].order_id == order.id
    assert rows[0].is_read is False


async def test_handle_order_paid_idempotent(session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)

    assert await handle_order_paid(session, order.id) is True
    assert await handle_order_paid(session, order.id) is False  # 중복 이벤트 → no-op

    count = (await session.execute(select(func.count()).select_from(Notification))).scalar()
    assert count == 1


async def test_handle_order_paid_unknown_order(session: AsyncSession):
    assert await handle_order_paid(session, 99999999) is False
