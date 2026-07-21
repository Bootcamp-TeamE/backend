from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus


async def restore_stock(session: AsyncSession, sale_id: int, quantity: int) -> None:
    """취소·만료 시 재고를 되돌리는 보상 트랜잭션. 호출자가 멱등 가드로 1회만 부른다."""
    await session.execute(
        update(Sale)
        .where(Sale.id == sale_id)
        .values(remaining_quantity=Sale.remaining_quantity + quantity)
        .execution_options(synchronize_session=False)
    )
    # 품절로 닫혔던 세일만 다시 연다. 수동 마감(CLOSED)은 건드리지 않는다.
    await session.execute(
        update(Sale)
        .where(Sale.id == sale_id, Sale.status == SaleStatus.SOLDOUT)
        .values(status=SaleStatus.ACTIVE)
        .execution_options(synchronize_session=False)
    )


async def expire_order(session: AsyncSession, order_id: int) -> bool:
    """예약 1건을 만료 처리하는 멱등 코어. 상태 조건부 전이가 멱등 가드다.

    reserved일 때만 expired로 전이하고 재고를 원복한다. 커밋은 호출자 책임.
    보장 계층(sweep)과 즉시 계층(Redis TTL 리스너)이 이 함수를 공유한다.
    이미 결제·취소·만료된 주문이면 0행 → 아무것도 하지 않고 False.
    """
    row = (
        await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.RESERVED)
            .values(status=OrderStatus.EXPIRED)
            .returning(Order.quantity, Order.sale_id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        return False
    quantity, sale_id = row
    await restore_stock(session, sale_id, quantity)
    return True


async def sweep_expired_orders(session: AsyncSession, now: datetime | None = None) -> int:
    """예약(reserved) 상태로 만료시각이 지난 주문을 일괄 만료 처리한다(보장 계층)."""
    now = now or datetime.now(timezone.utc)
    ids = (
        await session.execute(
            select(Order.id).where(
                Order.status == OrderStatus.RESERVED,
                Order.expires_at < now,
                Order.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    expired = 0
    for order_id in ids:
        if await expire_order(session, order_id):
            expired += 1

    await session.commit()
    return expired
