"""즉시 만료 계층(Redis TTL 키 → 멱등 코어 디스패치) 테스트.

Redis 배관은 통합 영역이라 여기선 순수 디스패처 handle_expired_key만 검증한다.
(보장 계층 sweep과 같은 expire_order/refund_order 코어를 공유하므로 멱등·상태가드가 동일.)
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.sale import Sale
from app.services.order import handle_expired_key, pickup_ttl_key, reserve_ttl_key
from tests.order.helpers import seed_sale, seed_user


async def _order(client: AsyncClient, user_id: int, sale_id: int, quantity: int = 1):
    return await client.post(
        "/api/v1/orders", json={"user_id": user_id, "sale_id": sale_id, "quantity": quantity}
    )


async def _pay(client: AsyncClient, order_id: int):
    return await client.post(f"/api/v1/orders/{order_id}/pay")


def test_ttl_key_format():
    assert reserve_ttl_key(7) == "order:expire:7"
    assert pickup_ttl_key(7) == "order:pickup:7"


async def test_reserve_key_expires_reserved_and_restores_stock(
    client: AsyncClient, session: AsyncSession
):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]

    result = await handle_expired_key(session, reserve_ttl_key(order_id))
    assert result == ("expired", order_id)

    order = await session.get(Order, order_id)
    await session.refresh(order)
    assert order.status == OrderStatus.EXPIRED
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5  # 재고 원복


async def test_reserve_key_noop_on_paid(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]
    await _pay(client, order_id)

    assert await handle_expired_key(session, reserve_ttl_key(order_id)) is None  # 이미 결제됨


async def test_pickup_key_refunds_paid(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5, deadline_hours=2)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=1)).json()["id"]
    await _pay(client, order_id)

    result = await handle_expired_key(session, pickup_ttl_key(order_id))
    assert result == ("refunded", order_id)

    order = await session.get(Order, order_id)
    await session.refresh(order)
    assert order.status == OrderStatus.REFUNDED


async def test_pickup_key_noop_on_reserved(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id)).json()["id"]  # 결제 전

    assert await handle_expired_key(session, pickup_ttl_key(order_id)) is None


async def test_reserve_key_idempotent(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]

    assert await handle_expired_key(session, reserve_ttl_key(order_id)) == ("expired", order_id)
    assert await handle_expired_key(session, reserve_ttl_key(order_id)) is None  # 재호출 no-op
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5  # 원복은 정확히 한 번


async def test_unknown_key_ignored(session: AsyncSession):
    assert await handle_expired_key(session, "some:unrelated:key") is None
    assert await handle_expired_key(session, "order:expire:notanint") is None
