from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _owner(session: AsyncSession, i: int = 1) -> User:
    user = User(email=f"owner{i}@test.local", google_sub=f"osub-{i}", role=Role.OWNER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _plain_user(session: AsyncSession, i: int = 1) -> User:
    user = User(email=f"user{i}@test.local", google_sub=f"usub-{i}", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _store(session: AsyncSession, owner: User) -> Store:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="piece"))
    store = Store(owner_id=owner.id, category_code="butcher", name="정육점", lat=37.58, lng=127.04)
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store


async def _sale(session: AsyncSession, store: Store) -> Sale:
    sale = Sale(
        store_id=store.id,
        category_code="butcher",
        title="한우 8팩",
        normal_price=4000,
        sale_price=2000,
        unit_code="piece",
        total_quantity=8,
        remaining_quantity=8,
        deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
        status=SaleStatus.ACTIVE,
    )
    session.add(sale)
    await session.commit()
    await session.refresh(sale)
    return sale


def _body(**over) -> dict:
    b = {
        "title": "한우 8팩", "normal_price": 4000, "sale_price": 2000, "total_quantity": 8,
        "deadline_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }
    b.update(over)
    return b


async def test_create_sale_anonymous_401(client: AsyncClient, session: AsyncSession):
    owner = await _owner(session)
    store = await _store(session, owner)
    resp = await client.post(f"/api/v1/stores/{store.id}/sales", json=_body())
    assert resp.status_code == 401


async def test_create_sale_other_owner_403(client: AsyncClient, session: AsyncSession):
    owner = await _owner(session, i=1)
    store = await _store(session, owner)
    other_owner = await _owner(session, i=2)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(other_owner)
    )
    assert resp.status_code == 403


async def test_create_sale_plain_user_403(client: AsyncClient, session: AsyncSession):
    owner = await _owner(session)
    store = await _store(session, owner)
    plain = await _plain_user(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(plain)
    )
    assert resp.status_code == 403


async def test_create_sale_owner_ok_201(client: AsyncClient, session: AsyncSession):
    owner = await _owner(session)
    store = await _store(session, owner)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
    )
    assert resp.status_code == 201


async def test_update_sale_other_owner_403(client: AsyncClient, session: AsyncSession):
    owner = await _owner(session, i=1)
    store = await _store(session, owner)
    sale = await _sale(session, store)
    other_owner = await _owner(session, i=2)
    resp = await client.patch(
        f"/api/v1/sales/{sale.id}", json={"status": "closed"}, headers=auth_headers(other_owner)
    )
    assert resp.status_code == 403


async def test_update_sale_owner_ok_200(client: AsyncClient, session: AsyncSession):
    owner = await _owner(session)
    store = await _store(session, owner)
    sale = await _sale(session, store)
    resp = await client.patch(
        f"/api/v1/sales/{sale.id}", json={"status": "closed"}, headers=auth_headers(owner)
    )
    assert resp.status_code == 200
