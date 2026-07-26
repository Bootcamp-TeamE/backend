from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import bus
from app.models.notification import Notification, NotificationType
from app.models.order import Order


async def _create_order_notification(
    session: AsyncSession, order_id: int, ntype: NotificationType
) -> bool:
    """주문 관련 개인 알림을 멱등 생성한다.

    UNIQUE(order_id, type) 위에서 ON CONFLICT DO NOTHING으로 원자·멱등 처리한다.
    이벤트 중복·재배달 시 두 번째부터 0행 → False. 커밋은 이 함수가 수행하고,
    새 알림일 때만 유저 SSE로 push한다.
    """
    order = await session.get(Order, order_id)
    if order is None:
        return False

    stmt = (
        pg_insert(Notification)
        .values(user_id=order.user_id, order_id=order.id, type=ntype)
        .on_conflict_do_nothing(index_elements=["order_id", "type"])
        .returning(Notification.id)
    )
    inserted = (await session.execute(stmt)).first()
    await session.commit()
    if inserted is not None:
        await bus.publish(bus.USER, order.user_id)
    return inserted is not None


async def handle_order_paid(session: AsyncSession, order_id: int) -> bool:
    """order.paid 이벤트 핸들러 — 구매자에게 결제 완료 알림."""
    return await _create_order_notification(session, order_id, NotificationType.ORDER_PAID)


async def handle_order_picked_up(session: AsyncSession, order_id: int) -> bool:
    """order.picked_up 이벤트 핸들러 — 구매자에게 픽업 완료 알림.

    픽업은 점주 QR 확인으로 트리거되므로 구매자에겐 거래 종료 확인 알림이 유용하다.
    """
    return await _create_order_notification(session, order_id, NotificationType.ORDER_PICKED_UP)


async def handle_order_refunded(session: AsyncSession, order_id: int) -> bool:
    """픽업 데드라인 경과로 자동 환불된 주문 — 구매자에게 환불 안내 알림."""
    return await _create_order_notification(session, order_id, NotificationType.ORDER_REFUNDED)
