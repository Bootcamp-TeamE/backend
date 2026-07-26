from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.user import User
from app.services.order import (
    expire_order,
    refund_order,
    sweep_expired_orders,
    sweep_pickup_expired_orders,
)
from tests.conftest import auth_headers
from tests.order.helpers import seed_sale, seed_user


async def _order(client: AsyncClient, user: User, sale_id: int, quantity: int = 1):
    return await client.post(
        "/api/v1/orders",
        json={"sale_id": sale_id, "quantity": quantity},
        headers=auth_headers(user),
    )


async def _pay(client: AsyncClient, order_id: int, user: User):
    return await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))


async def test_create_order_reserves_and_computes_price(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5, sale_price=2000)
    user = await seed_user(session)
    resp = await _order(client, user, sale.id, quantity=2)
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
    resp = await _order(client, user, 99999999)
    assert resp.status_code == 404


async def test_create_order_below_min_order(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=1000, min_order=100)
    user = await seed_user(session)
    resp = await _order(client, user, sale.id, quantity=50)
    assert resp.status_code == 422


async def test_create_order_soldout_sale(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, status=SaleStatus.SOLDOUT)
    user = await seed_user(session)
    resp = await _order(client, user, sale.id)
    assert resp.status_code == 409


async def test_pay_issues_qr_and_pickup_no(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id)).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid"
    assert body["qr_token"] is not None
    assert body["pickup_no"] is not None


async def test_pay_twice_conflicts(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id)).json()["id"]
    assert (await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))).status_code == 200
    assert (await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))).status_code == 409


async def test_cancel_restores_stock(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/cancel", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5


async def test_cancel_idempotent_no_double_restore(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]
    assert (await client.post(f"/api/v1/orders/{order_id}/cancel", headers=auth_headers(user))).status_code == 200
    assert (await client.post(f"/api/v1/orders/{order_id}/cancel", headers=auth_headers(user))).status_code == 409

    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5  # 원복은 정확히 한 번


async def test_cancel_reactivates_soldout_sale(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=1)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=1)).json()["id"]

    soldout = await session.get(Sale, sale.id)
    await session.refresh(soldout)
    assert soldout.status == SaleStatus.SOLDOUT

    await client.post(f"/api/v1/orders/{order_id}/cancel", headers=auth_headers(user))
    reactivated = await session.get(Sale, sale.id)
    await session.refresh(reactivated)
    assert reactivated.remaining_quantity == 1
    assert reactivated.status == SaleStatus.ACTIVE


async def test_pickup_after_pay(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id)).json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))
    resp = await client.post(f"/api/v1/orders/{order_id}/pickup", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["status"] == "picked_up"


async def test_pickup_without_pay_conflicts(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id)).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/pickup", headers=auth_headers(user))
    assert resp.status_code == 409


async def test_get_order_and_not_found(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id)).json()["id"]
    assert (await client.get(f"/api/v1/orders/{order_id}", headers=auth_headers(user))).status_code == 200
    assert (
        await client.get("/api/v1/orders/99999999", headers=auth_headers(user))
    ).status_code == 404


async def test_list_orders_by_user(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    buyer = await seed_user(session, i=1)
    other = await seed_user(session, i=2)
    await _order(client, buyer, sale.id)
    await _order(client, other, sale.id)
    resp = await client.get("/api/v1/orders", headers=auth_headers(buyer))
    assert resp.status_code == 200
    assert [o["user_id"] for o in resp.json()] == [buyer.id]


async def test_sweep_expires_reserved_and_restores_stock(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]

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
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]

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
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))

    assert await expire_order(session, order_id) is False
    await session.commit()
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 3  # 결제된 주문은 만료·원복 대상 아님


# ── 예약 홀드 시간(5분) ──


async def test_reservation_hold_is_five_minutes(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    body = (await _order(client, user, sale.id)).json()
    reserved = datetime.fromisoformat(body["reserved_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert (expires - reserved) == timedelta(minutes=5)


async def test_pay_after_expiry_conflicts_and_restores_stock(
    client: AsyncClient, session: AsyncSession
):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]

    order = await session.get(Order, order_id)
    order.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await session.commit()

    resp = await _pay(client, order_id, user)
    assert resp.status_code == 409

    await session.refresh(order)
    assert order.status == OrderStatus.EXPIRED
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5  # 만료로 재고 원복


# ── 픽업 만료(30분) → 환불 ──


async def test_refund_before_deadline_restores_stock(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5, deadline_hours=2)  # 마감 아직 안 됨
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]
    await _pay(client, order_id, user)

    assert await refund_order(session, order_id) is True
    await session.commit()

    order = await session.get(Order, order_id)
    await session.refresh(order)
    assert order.status == OrderStatus.REFUNDED
    assert order.refunded_at is not None
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 5  # 마감 전이라 재고 원복


async def test_refund_after_deadline_keeps_stock(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5, deadline_hours=2)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]
    await _pay(client, order_id, user)

    s = await session.get(Sale, sale.id)
    s.deadline_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # 마감 지남
    await session.commit()

    assert await refund_order(session, order_id) is True
    await session.commit()
    fresh = await session.get(Sale, sale.id)
    await session.refresh(fresh)
    assert fresh.remaining_quantity == 3  # 마감 후라 재고 원복 안 함


async def test_refund_idempotent_and_noop_on_non_paid(
    client: AsyncClient, session: AsyncSession
):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=2)).json()["id"]

    assert await refund_order(session, order_id) is False  # reserved는 환불 대상 아님
    await _pay(client, order_id, user)
    assert await refund_order(session, order_id) is True
    await session.commit()
    assert await refund_order(session, order_id) is False  # 재호출 no-op


async def test_sweep_pickup_expired_refunds_paid(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5, deadline_hours=2)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=1)).json()["id"]
    await _pay(client, order_id, user)

    order = await session.get(Order, order_id)
    order.paid_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    await session.commit()

    refunded = await sweep_pickup_expired_orders(session)
    assert order_id in refunded

    await session.refresh(order)
    assert order.status == OrderStatus.REFUNDED


async def test_sweep_pickup_leaves_recent_paid(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session, remaining=5)
    user = await seed_user(session)
    order_id = (await _order(client, user, sale.id, quantity=1)).json()["id"]
    await _pay(client, order_id, user)  # 방금 결제 → 30분 안 지남

    refunded = await sweep_pickup_expired_orders(session)
    assert order_id not in refunded
    order = await session.get(Order, order_id)
    await session.refresh(order)
    assert order.status == OrderStatus.PAID
