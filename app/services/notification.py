from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.order import Order


async def handle_order_paid(session: AsyncSession, order_id: int) -> bool:
    """order.paid 이벤트 핸들러. 구매자에게 결제 완료 알림을 멱등 생성한다.

    UNIQUE(order_id, type) 위에서 ON CONFLICT DO NOTHING으로 원자·멱등 처리한다.
    이벤트 중복·재배달 시 두 번째부터 0행 → False. 커밋은 이 함수가 수행.
    """
    order = await session.get(Order, order_id)
    if order is None:
        return False

    stmt = (
        pg_insert(Notification)
        .values(user_id=order.user_id, order_id=order.id, type=NotificationType.ORDER_PAID)
        .on_conflict_do_nothing(index_elements=["order_id", "type"])
        .returning(Notification.id)
    )
    inserted = (await session.execute(stmt)).first()
    await session.commit()
    return inserted is not None
