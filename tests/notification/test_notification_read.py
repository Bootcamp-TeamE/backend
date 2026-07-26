from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.notification import handle_order_paid
from tests.conftest import auth_headers
from tests.notification.test_notification_service import _paid_order
from tests.order.helpers import seed_sale, seed_user


async def _make_notification(session: AsyncSession, user, sale):
    order = await _paid_order(session, user, sale)
    await handle_order_paid(session, order.id)
    return order


async def test_unread_count(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    await _make_notification(session, user, sale)

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


async def test_list_unread_filter(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    await _make_notification(session, user, sale)
    await _make_notification(session, user, sale)

    listed = (
        await client.get("/api/v1/notifications", headers=auth_headers(user))
    ).json()
    assert len(listed) == 2
    oldest_id = listed[-1]["id"]
    await client.patch(f"/api/v1/notifications/{oldest_id}/read", headers=auth_headers(user))

    unread = (
        await client.get(
            "/api/v1/notifications", params={"unread": True}, headers=auth_headers(user)
        )
    ).json()
    assert len(unread) == 1
    assert unread[0]["is_read"] is False


async def test_mark_all_read(client: AsyncClient, session: AsyncSession):
    sale = await seed_sale(session)
    user = await seed_user(session)
    await _make_notification(session, user, sale)
    await _make_notification(session, user, sale)

    resp = await client.patch("/api/v1/notifications/read-all", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    count = (
        await client.get("/api/v1/notifications/unread-count", headers=auth_headers(user))
    ).json()["count"]
    assert count == 0
