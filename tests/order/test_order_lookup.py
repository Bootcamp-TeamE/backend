from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.order.helpers import seed_sale, seed_user


async def _paid_order(client: AsyncClient, session: AsyncSession) -> dict:
    sale = await seed_sale(session)
    user = await seed_user(session)
    created = await client.post(
        "/api/v1/orders", json={"user_id": user.id, "sale_id": sale.id, "quantity": 1}
    )
    order_id = created.json()["id"]
    pay = await client.post(f"/api/v1/orders/{order_id}/pay")
    return pay.json()


async def test_lookup_by_pickup_no(client: AsyncClient, session: AsyncSession):
    order = await _paid_order(client, session)
    resp = await client.get("/api/v1/orders/lookup", params={"code": order["pickup_no"]})
    assert resp.status_code == 200
    assert resp.json()["id"] == order["id"]


async def test_lookup_by_qr_token(client: AsyncClient, session: AsyncSession):
    order = await _paid_order(client, session)
    resp = await client.get("/api/v1/orders/lookup", params={"code": order["qr_token"]})
    assert resp.status_code == 200
    assert resp.json()["id"] == order["id"]


async def test_lookup_unknown_code_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/orders/lookup", params={"code": "NOPE"})
    assert resp.status_code == 404
