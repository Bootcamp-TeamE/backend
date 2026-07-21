from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.services.order import expire_order, sweep_expired_orders
from tests.order.helpers import seed_sale, seed_user


async def _order(client: AsyncClient, user_id: int, sale_id: int, quantity: int = 1):
    return await client.post(
        "/api/v1/orders", json={"user_id": user_id, "sale_id": sale_id, "quantity": quantity}
    )


async def test_create_order_reserves_and_computes_price(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5, sale_price=2000)
    user = await seed_user(session)
    resp = await _order(client, user.id, sale.id, quantity=2)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "reserved"
    assert body["total_price"] == 4000
    assert body["expires_at"] is not None

    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 3


async def test_create_order_sale_not_found(client: AsyncClient, session: AsyncSession):
    user = await seed_user(session)
    resp = await _order(client, user.id, 99999999)
    assert resp.status_code == 404


async def test_create_order_user_not_found(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    resp = await _order(client, 99999999, sale.id)
    assert resp.status_code == 404


async def test_create_order_below_min_order(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=1000, min_order=100)
    user = await seed_user(session)
    resp = await _order(client, user.id, sale.id, quantity=50)
    assert resp.status_code == 422


async def test_create_order_soldout_sale(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, status=SaleStatus.SOLDOUT)
    user = await seed_user(session)
    resp = await _order(client, user.id, sale.id)
    assert resp.status_code == 409


async def test_pay_issues_qr_and_pickup_no(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id)).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/pay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert body["qr_token"] is not None
    assert body["pickup_no"] is not None


async def test_pay_twice_conflicts(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id)).json()["id"]
    assert (await client.post(f"/api/v1/orders/{order_id}/pay")).status_code == 200
    assert (await client.post(f"/api/v1/orders/{order_id}/pay")).status_code == 409


async def test_cancel_restores_stock(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5


async def test_cancel_idempotent_no_double_restore(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]
    assert (await client.post(f"/api/v1/orders/{order_id}/cancel")).status_code == 200
    assert (await client.post(f"/api/v1/orders/{order_id}/cancel")).status_code == 409

    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5  # 원복은 정확히 한 번


async def test_cancel_reactivates_soldout_sale(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=1)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=1)).json()["id"]

    soldout = await session.get(Sale, sale.id)
    await session.refresh(soldout)
    assert soldout.status == SaleStatus.SOLDOUT

    await client.post(f"/api/v1/orders/{order_id}/cancel")
    reactivated = await session.get(Sale, sale.id)
    await session.refresh(reactivated)
    assert reactivated.remaining_quantity == 1
    assert reactivated.status == SaleStatus.ACTIVE


async def test_pickup_after_pay(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id)).json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/pay")
    resp = await client.post(f"/api/v1/orders/{order_id}/pickup")
    assert resp.status_code == 200
    assert resp.json()["status"] == "picked_up"


async def test_pickup_without_pay_conflicts(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id)).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/pickup")
    assert resp.status_code == 409


async def test_get_order_and_not_found(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id)).json()["id"]
    assert (await client.get(f"/api/v1/orders/{order_id}")).status_code == 200
    assert (await client.get("/api/v1/orders/99999999")).status_code == 404


async def test_list_orders_by_user(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    buyer = await seed_user(session, i=1)
    other = await seed_user(session, i=2)
    await _order(client, buyer.id, sale.id)
    await _order(client, other.id, sale.id)
    resp = await client.get("/api/v1/orders", params={"user_id": buyer.id})
    assert resp.status_code == 200
    assert [o["user_id"] for o in resp.json()] == [buyer.id]


async def test_sweep_expires_reserved_and_restores_stock(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    order = await session.get(Order, order_id)
    order.expires_at = past
    await session.commit()

    swept = await sweep_expired_orders(session)
    assert swept == 1

    await session.refresh(order)
    assert order.status == OrderStatus.EXPIRED
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5


async def test_expire_order_idempotent_restores_once(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]

    assert await expire_order(session, order_id) is True
    await session.commit()
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5

    # 재호출은 no-op — 재고를 두 번 되돌리지 않는다.
    assert await expire_order(session, order_id) is False
    await session.commit()
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5


async def test_expire_order_noop_on_paid(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user.id, sale.id, quantity=2)).json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/pay")

    assert await expire_order(session, order_id) is False
    await session.commit()
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 3  # 결제된 주문은 만료·원복 대상 아님
