from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.conftest import auth_headers
from tests.order.helpers import seed_sale, seed_user


async def _paid_order(client: AsyncClient, session: AsyncSession) -> tuple[dict, User]:
    sale = await seed_sale(session)
    user = await seed_user(session)
    created = await client.post(
        "/api/v1/orders",
        json={"sale_id": sale.id, "quantity": 1},
        headers=auth_headers(user),
    )
    order_id = created.json()["id"]
    pay = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(user))
    return pay.json(), user


async def test_lookup_by_pickup_no(client: AsyncClient, session: AsyncSession):
    order, user = await _paid_order(client, session)
    resp = await client.get(
        "/api/v1/orders/lookup", params={"code": order["pickup_no"]}, headers=auth_headers(user)
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == order["id"]


async def test_lookup_by_qr_token(client: AsyncClient, session: AsyncSession):
    order, user = await _paid_order(client, session)
    resp = await client.get(
        "/api/v1/orders/lookup", params={"code": order["qr_token"]}, headers=auth_headers(user)
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == order["id"]


async def test_lookup_unknown_code_not_found(client: AsyncClient, session: AsyncSession):
    user = await seed_user(session)
    resp = await client.get(
        "/api/v1/orders/lookup", params={"code": "NOPE"}, headers=auth_headers(user)
    )
    assert resp.status_code == 404
