from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_log import NotificationLog
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.store import Store


async def get_owner_store_id(session: AsyncSession, owner_id: int) -> int | None:
    """점주(owner_id)의 매장 id. 1계정=1매장이라 최대 1개."""
    return (
        await session.execute(
            select(Store.id).where(Store.owner_id == owner_id, Store.is_deleted.is_(False))
        )
    ).scalar()


async def compute_dashboard(session: AsyncSession, owner_id: int) -> dict | None:
    """점주 대시보드 요약 지표 스냅샷. 매장이 없으면 None."""
    store_id = await get_owner_store_id(session, owner_id)
    if store_id is None:
        return None

    now = datetime.now(timezone.utc)
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    active_sales = (
        await session.execute(
            select(func.count())
            .select_from(Sale)
            .where(
                Sale.store_id == store_id,
                Sale.status == SaleStatus.ACTIVE,
                Sale.deadline_at > now,
                Sale.is_deleted.is_(False),
            )
        )
    ).scalar()

    # 오늘 판매(결제) 건수·판매액(손실 회수액). 결제된(paid|picked_up) 주문 기준.
    paid_stmt = (
        select(func.count(), func.coalesce(func.sum(Order.total_price), 0))
        .select_from(Order)
        .join(Sale, Order.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Order.status.in_([OrderStatus.PAID, OrderStatus.PICKED_UP]),
            Order.paid_at >= day_start,
        )
    )
    today_orders, today_revenue = (await session.execute(paid_stmt)).one()

    total_reach = (
        await session.execute(
            select(func.count())
            .select_from(NotificationLog)
            .join(Sale, NotificationLog.sale_id == Sale.id)
            .where(Sale.store_id == store_id)
        )
    ).scalar()

    return {
        "owner_id": owner_id,
        "store_id": store_id,
        "active_sales": active_sales,
        "today_orders": today_orders,
        "today_revenue": today_revenue,
        "total_reach": total_reach,
    }
