import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.events import bus
from app.events.publisher import EventPublisher, get_publisher
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import User
from app.schemas.order import OrderCreate, OrderResponse
from app.services.order import expire_order, restore_stock

logger = logging.getLogger(__name__)

router = APIRouter(tags=["주문"])

RESERVE_HOLD_MINUTES = 5


async def _notify_owner_dashboard(session: AsyncSession, sale_id: int) -> None:
    """주문 변경을 해당 매장 점주의 대시보드 SSE로 깨우기. sale→store→owner 유도."""
    sale = await session.get(Sale, sale_id)
    if sale is None:
        return
    store = await session.get(Store, sale.store_id)
    if store is not None and store.owner_id is not None:
        await bus.publish(bus.DASHBOARD, store.owner_id)


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="주문·예약 생성",
)
async def create_order(
    payload: OrderCreate, session: AsyncSession = Depends(get_session)
) -> Order:
    sale = await session.get(Sale, payload.sale_id)
    if sale is None or sale.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.SALE_NOT_FOUND)
    if await session.get(User, payload.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.USER_NOT_FOUND)
    if payload.quantity < sale.min_order:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.BELOW_MIN_ORDER)

    now = datetime.now(timezone.utc)
    if sale.status != SaleStatus.ACTIVE or sale.deadline_at <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.SALE_NOT_ORDERABLE)

    # 원자 조건부 차감: 재고가 충분할 때만 1행이 갱신된다. 동시성 하에서도 오버셀이 없다.
    remaining = (
        await session.execute(
            update(Sale)
            .where(Sale.id == sale.id, Sale.remaining_quantity >= payload.quantity)
            .values(remaining_quantity=Sale.remaining_quantity - payload.quantity)
            .returning(Sale.remaining_quantity)
            .execution_options(synchronize_session=False)
        )
    ).scalar()
    if remaining is None:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.INSUFFICIENT_STOCK)

    if remaining == 0:
        await session.execute(
            update(Sale)
            .where(Sale.id == sale.id)
            .values(status=SaleStatus.SOLDOUT)
            .execution_options(synchronize_session=False)
        )

    order = Order(
        user_id=payload.user_id,
        sale_id=sale.id,
        quantity=payload.quantity,
        total_price=payload.quantity * sale.sale_price,
        status=OrderStatus.RESERVED,
        reserved_at=now,
        expires_at=now + timedelta(minutes=RESERVE_HOLD_MINUTES),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    await _notify_owner_dashboard(session, sale.id)
    return order


@router.get("/orders", response_model=list[OrderResponse], summary="내 주문·예약 목록")
async def list_orders(
    user_id: int, session: AsyncSession = Depends(get_session)
) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id, Order.is_deleted.is_(False))
        .order_by(Order.reserved_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/orders/lookup", response_model=OrderResponse, summary="QR·픽업번호로 주문 조회")
async def lookup_order(code: str, session: AsyncSession = Depends(get_session)) -> Order:
    """점주 QR 확인용. qr_token 또는 pickup_no 로 주문을 찾는다.
    경로 특성상 `/orders/{order_id}` 보다 먼저 선언해야 'lookup'이 int로 파싱되지 않는다."""
    order = (
        await session.execute(
            select(Order).where(
                or_(Order.qr_token == code, Order.pickup_no == code),
                Order.is_deleted.is_(False),
            )
        )
    ).scalars().first()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.ORDER_NOT_FOUND)
    return order


@router.get("/orders/{order_id}", response_model=OrderResponse, summary="주문·예약 상세")
async def get_order(order_id: int, session: AsyncSession = Depends(get_session)) -> Order:
    order = await session.get(Order, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.ORDER_NOT_FOUND)
    return order


@router.post("/orders/{order_id}/pay", response_model=OrderResponse, summary="주문 결제")
async def pay_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    publisher: EventPublisher = Depends(get_publisher),
) -> Order:
    order = await session.get(Order, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.ORDER_NOT_FOUND)

    # sweep가 아직 안 돌았어도 만료시각이 지난 예약은 결제 불가. 즉시 만료 처리하고 거절.
    if order.status == OrderStatus.RESERVED and order.expires_at <= datetime.now(timezone.utc):
        await expire_order(session, order_id)
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.RESERVATION_EXPIRED)

    changed = (
        await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.RESERVED)
            .values(
                status=OrderStatus.PAID,
                paid_at=datetime.now(timezone.utc),
                qr_token=uuid4().hex,
                pickup_no=f"{order_id:06d}",
            )
            .returning(Order.id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if changed is None:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.INVALID_ORDER_STATE)

    await session.commit()
    await session.refresh(order)

    # 알림은 best-effort — 발행 실패해도 결제는 이미 커밋됨. sweep/재조회로 상태 확인 가능.
    try:
        await publisher.publish("order.paid", {"order_id": order.id})
    except Exception:
        logger.exception("order.paid 이벤트 발행 실패 order_id=%s", order.id)

    await _notify_owner_dashboard(session, order.sale_id)
    return order


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse, summary="주문 취소")
async def cancel_order(order_id: int, session: AsyncSession = Depends(get_session)) -> Order:
    order = await session.get(Order, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.ORDER_NOT_FOUND)

    # 상태 조건부 전이가 멱등 가드다. 1행일 때만 보상(재고 원복)을 정확히 한 번 수행한다.
    row = (
        await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status.in_([OrderStatus.RESERVED, OrderStatus.PAID]))
            .values(status=OrderStatus.CANCELLED)
            .returning(Order.quantity, Order.sale_id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.INVALID_ORDER_STATE)

    quantity, sale_id = row
    await restore_stock(session, sale_id, quantity)
    await session.commit()
    await session.refresh(order)
    await _notify_owner_dashboard(session, order.sale_id)
    return order


@router.post("/orders/{order_id}/pickup", response_model=OrderResponse, summary="주문 수령")
async def pickup_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    publisher: EventPublisher = Depends(get_publisher),
) -> Order:
    order = await session.get(Order, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.ORDER_NOT_FOUND)

    changed = (
        await session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.PAID)
            .values(status=OrderStatus.PICKED_UP, picked_up_at=datetime.now(timezone.utc))
            .returning(Order.id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if changed is None:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.INVALID_ORDER_STATE)

    await session.commit()
    await session.refresh(order)

    # 알림은 best-effort — 발행 실패해도 픽업은 이미 커밋됨.
    try:
        await publisher.publish("order.picked_up", {"order_id": order.id})
    except Exception:
        logger.exception("order.picked_up 이벤트 발행 실패 order_id=%s", order.id)

    await _notify_owner_dashboard(session, order.sale_id)
    return order
