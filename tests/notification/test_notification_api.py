from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import FakePublisher
from app.services.notification import handle_order_paid
from tests.notification.test_notification_service import _paid_order
from tests.order.helpers import seed_sale, seed_user


async def test_pay_publishes_order_paid_event(
    client: AsyncClient, session: AsyncSession, fake_publisher: FakePublisher
):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order_id = (
        await client.post(
            "/api/v1/orders", json={"user_id": user.id, "sale_id": sale.id, "quantity": 1}
        )
    ).json()["id"]

    await client.post(f"/api/v1/orders/{order_id}/pay")

    assert ("order.paid", {"order_id": order_id}) in fake_publisher.events


async def test_reserve_does_not_publish(
    client: AsyncClient, session: AsyncSession, fake_publisher: FakePublisher
):
    sale = await seed_sale(session)
    user = await seed_user(session)
    await client.post(
        "/api/v1/orders", json={"user_id": user.id, "sale_id": sale.id, "quantity": 1}
    )
    assert fake_publisher.events == []  # 예약만으로는 알림 이벤트 없음


async def test_list_notifications(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)
    await handle_order_paid(session, order.id)

    resp = await client.get("/api/v1/notifications", params={"user_id": user.id})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["type"] == "order_paid"
    assert body[0]["order_id"] == order.id
    assert body[0]["is_read"] is False


async def test_mark_notification_read(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    order = await _paid_order(session, user, sale)
    await handle_order_paid(session, order.id)
    notif_id = (await client.get("/api/v1/notifications", params={"user_id": user.id})).json()[0]["id"]

    resp = await client.patch(f"/api/v1/notifications/{notif_id}/read")
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


async def test_mark_notification_read_not_found(client: AsyncClient):
    resp = await client.patch("/api/v1/notifications/99999999/read")
    assert resp.status_code == 404
