from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus

# 결제 후 이 시간 안에 픽업하지 않으면 no-show로 자동 환불한다.
PICKUP_HOLD_MINUTES = 30


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


async def refund_order(session: AsyncSession, order_id: int, now: datetime | None = None) -> bool:
    """결제 완료 주문 1건을 환불 처리하는 멱등 코어(no-show). 커밋은 호출자 책임.

    paid일 때만 refunded로 전이한다(상태 조건부 전이가 멱등 가드). 재고는 세일 마감
    전이면 재판매 가능하므로 원복하고, 마감 후면 폐기 성격이라 원복하지 않는다.
    이미 픽업·취소·환불된 주문이면 0행 → False.
    """
    now = now or datetime.now(timezone.utc)
    row = (
        await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.PAID)
            .values(status=OrderStatus.REFUNDED, refunded_at=now)
            .returning(Order.quantity, Order.sale_id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        return False
    quantity, sale_id = row
    sale = await session.get(Sale, sale_id)
    if sale is not None and sale.deadline_at > now:
        await restore_stock(session, sale_id, quantity)
    return True


async def sweep_pickup_expired_orders(
    session: AsyncSession, now: datetime | None = None
) -> list[int]:
    """결제 후 픽업 데드라인(PICKUP_HOLD_MINUTES)이 지난 주문을 일괄 환불한다(보장 계층).

    환불된 주문 id 목록을 돌려준다. 호출자(워커)가 이 id로 환불 알림을 발송한다.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=PICKUP_HOLD_MINUTES)
    ids = (
        await session.execute(
            select(Order.id).where(
                Order.status == OrderStatus.PAID,
                Order.paid_at < cutoff,
                Order.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    refunded: list[int] = []
    for order_id in ids:
        if await refund_order(session, order_id, now=now):
            refunded.append(order_id)

    await session.commit()
    return refunded


# ── 즉시 만료 계층(Redis TTL 키) ──
# 예약/결제 시 TTL 키를 걸고, 키 만료 이벤트가 오면 아래 디스패처가 멱등 코어를 호출한다.
# 보장 계층(sweep)과 같은 expire_order/refund_order를 공유하므로 중복 실행돼도 안전.

EXPIRE_KEY_PREFIX = "order:expire:"  # 예약 만료(5분)
PICKUP_KEY_PREFIX = "order:pickup:"  # 픽업 데드라인(30분) → no-show 환불


def reserve_ttl_key(order_id: int) -> str:
    return f"{EXPIRE_KEY_PREFIX}{order_id}"


def pickup_ttl_key(order_id: int) -> str:
    return f"{PICKUP_KEY_PREFIX}{order_id}"


def _parse_expiry_key(key: str) -> tuple[str, int] | None:
    for kind, prefix in (("expire", EXPIRE_KEY_PREFIX), ("pickup", PICKUP_KEY_PREFIX)):
        if key.startswith(prefix):
            try:
                return kind, int(key[len(prefix):])
            except ValueError:
                return None
    return None


async def handle_expired_key(
    session: AsyncSession, key: str, now: datetime | None = None
) -> tuple[str, int] | None:
    """만료된 Redis TTL 키 1개를 처리한다(즉시 계층).

    order:expire:{id} → expire_order, order:pickup:{id} → refund_order.
    상태 조건부 전이가 멱등 가드라 이미 결제·픽업·취소된 건이면 no-op(None).
    성공 시 ('expired'|'refunded', order_id) 반환 — 호출자(리스너)가 환불 알림에 사용.
    우리 키가 아니거나 파싱 불가면 None.
    """
    parsed = _parse_expiry_key(key)
    if parsed is None:
        return None
    kind, order_id = parsed
    if kind == "expire":
        changed = await expire_order(session, order_id)
        outcome = ("expired", order_id)
    else:
        changed = await refund_order(session, order_id, now=now)
        outcome = ("refunded", order_id)
    if not changed:
        return None
    await session.commit()
    return outcome
