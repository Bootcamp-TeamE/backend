from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import bus
from app.models.notification import Notification, NotificationType
from app.models.notification_log import NotificationLog
from app.models.sale import Sale
from app.models.store import Store
from app.models.subscription import Subscription

DAILY_QUOTA = 10


async def handle_sale_created(
    session: AsyncSession, sale_id: int, now: datetime | None = None
) -> int:
    """sale.created 이벤트 핸들러. 반경·조건이 맞는 구독 유저에게 멱등 발송한다.

    매칭은 Postgres에서 수행(반경은 PostGIS ST_DistanceSphere). 유저별 일일 쿼터를 지키고,
    UNIQUE(sale_id, user_id) + ON CONFLICT DO NOTHING으로 중복 이벤트에도 발송 1건을 보장한다.
    발송 자체는 mock(notification_log 기록). 반환값은 새로 발송한 건수.
    """
    sale = await session.get(Sale, sale_id)
    if sale is None or sale.is_deleted:
        return 0
    store = await session.get(Store, sale.store_id)
    if store is None:
        return 0

    now = now or datetime.now(timezone.utc)
    hour = now.hour
    discount_rate = round((sale.normal_price - sale.sale_price) / sale.normal_price * 100)

    distance = func.ST_DistanceSphere(
        func.ST_MakePoint(store.lng, store.lat),
        func.ST_MakePoint(Subscription.lng, Subscription.lat),
    )
    stmt = select(Subscription.user_id).where(
        Subscription.is_deleted.is_(False),
        Subscription.opted_out.is_(False),
        Subscription.push_enabled.is_(True),
        Subscription.categories.any(sale.category_code),
        Subscription.min_discount_rate <= discount_rate,
        or_(Subscription.max_price.is_(None), Subscription.max_price >= sale.sale_price),
        Subscription.receive_from <= hour,
        Subscription.receive_to > hour,
        distance <= Subscription.radius_m,
    )
    user_ids = list(dict.fromkeys((await session.execute(stmt)).scalars()))  # 유저 중복 제거

    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    sent = 0
    notified: list[int] = []
    for user_id in user_ids:
        sent_today = (
            await session.execute(
                select(func.count())
                .select_from(NotificationLog)
                .where(NotificationLog.user_id == user_id, NotificationLog.created_at >= day_start)
            )
        ).scalar()
        if sent_today >= DAILY_QUOTA:
            continue
        inserted = (
            await session.execute(
                pg_insert(NotificationLog)
                .values(sale_id=sale.id, user_id=user_id)
                .on_conflict_do_nothing(index_elements=["sale_id", "user_id"])
                .returning(NotificationLog.id)
            )
        ).first()
        if inserted is not None:
            sent += 1
            # 발견 알림도 알림함(notifications)에 기록 → 인앱함·SSE에 노출.
            session.add(Notification(
                user_id=user_id, sale_id=sale.id, type=NotificationType.SALE_NEARBY,
            ))
            notified.append(user_id)

    await session.commit()
    for user_id in notified:  # 커밋 후 유저 SSE로 push
        await bus.publish(bus.USER, user_id)
    return sent
