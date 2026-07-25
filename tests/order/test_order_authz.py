from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers
from datetime import datetime, timedelta, timezone


async def _seed_sale(session: AsyncSession) -> int:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    store = Store(name="가게", category_code="butcher", lat=37.5, lng=127.0)
    session.add(store)
    await session.flush()
    sale = Sale(store_id=store.id, category_code="butcher", title="삼겹살", normal_price=10000,
                sale_price=6000, unit_code="geun", min_order=1, total_quantity=5,
                remaining_quantity=5, deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
                status=SaleStatus.ACTIVE)
    session.add(sale)
    await session.commit()
    return sale.id


async def _seed_sale_with_owner(session: AsyncSession, owner: User) -> int:
    """Create a sale whose store is owned by the given OWNER user."""
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    store = Store(name="가게", category_code="butcher", lat=37.5, lng=127.0, owner_id=owner.id)
    session.add(store)
    await session.flush()
    sale = Sale(store_id=store.id, category_code="butcher", title="삼겹살", normal_price=10000,
                sale_price=6000, unit_code="geun", min_order=1, total_quantity=5,
                remaining_quantity=5, deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
                status=SaleStatus.ACTIVE)
    session.add(sale)
    await session.commit()
    return sale.id


async def _user(session, i) -> User:
    u = User(email=f"u{i}@t.local", google_sub=f"s{i}", role=Role.USER)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_create_order_requires_auth(client: AsyncClient, session: AsyncSession):
    sale_id = await _seed_sale(session)
    resp = await client.post("/api/v1/orders", json={"sale_id": sale_id, "quantity": 1})
    assert resp.status_code == 401


async def test_create_order_binds_current_user(client: AsyncClient, session: AsyncSession):
    sale_id = await _seed_sale(session)
    user = await _user(session, 1)
    resp = await client.post(
        "/api/v1/orders", json={"sale_id": sale_id, "quantity": 1}, headers=auth_headers(user)
    )
    assert resp.status_code == 201
    assert resp.json()["user_id"] == user.id


async def test_cannot_pay_others_order(client: AsyncClient, session: AsyncSession):
    sale_id = await _seed_sale(session)
    owner_user = await _user(session, 1)
    attacker = await _user(session, 2)
    order_id = (await client.post(
        "/api/v1/orders", json={"sale_id": sale_id, "quantity": 1}, headers=auth_headers(owner_user)
    )).json()["id"]
    resp = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(attacker))
    assert resp.status_code == 403


async def test_list_orders_only_mine(client: AsyncClient, session: AsyncSession):
    sale_id = await _seed_sale(session)
    mine = await _user(session, 1)
    other = await _user(session, 2)
    await client.post("/api/v1/orders", json={"sale_id": sale_id, "quantity": 1}, headers=auth_headers(mine))
    resp = await client.get("/api/v1/orders", headers=auth_headers(other))
    assert resp.status_code == 200 and resp.json() == []


async def test_store_owner_can_view_buyers_order(client: AsyncClient, session: AsyncSession):
    owner = User(email="owner@t.local", google_sub="owner_sub", role=Role.OWNER)
    session.add(owner)
    await session.commit()
    await session.refresh(owner)

    sale_id = await _seed_sale_with_owner(session, owner)
    buyer = await _user(session, 1)

    order_id = (await client.post(
        "/api/v1/orders", json={"sale_id": sale_id, "quantity": 1}, headers=auth_headers(buyer)
    )).json()["id"]

    resp = await client.get(f"/api/v1/orders/{order_id}", headers=auth_headers(owner))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == buyer.id


async def test_store_owner_can_pickup_buyers_order(client: AsyncClient, session: AsyncSession):
    owner = User(email="owner@t.local", google_sub="owner_sub", role=Role.OWNER)
    session.add(owner)
    await session.commit()
    await session.refresh(owner)

    sale_id = await _seed_sale_with_owner(session, owner)
    buyer = await _user(session, 1)

    order_id = (await client.post(
        "/api/v1/orders", json={"sale_id": sale_id, "quantity": 1}, headers=auth_headers(buyer)
    )).json()["id"]

    await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers(buyer))

    resp = await client.post(f"/api/v1/orders/{order_id}/pickup", headers=auth_headers(owner))
    assert resp.status_code == 200
    assert resp.json()["status"] == "picked_up"


async def test_unrelated_owner_cannot_view_order(client: AsyncClient, session: AsyncSession):
    owner1 = User(email="owner1@t.local", google_sub="owner1_sub", role=Role.OWNER)
    owner2 = User(email="owner2@t.local", google_sub="owner2_sub", role=Role.OWNER)
    session.add(owner1)
    session.add(owner2)
    await session.commit()
    await session.refresh(owner1)
    await session.refresh(owner2)

    sale_id = await _seed_sale_with_owner(session, owner1)
    buyer = await _user(session, 1)

    order_id = (await client.post(
        "/api/v1/orders", json={"sale_id": sale_id, "quantity": 1}, headers=auth_headers(buyer)
    )).json()["id"]

    resp = await client.get(f"/api/v1/orders/{order_id}", headers=auth_headers(owner2))
    assert resp.status_code == 403
