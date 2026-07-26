from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _owner_with_store(session, i) -> User:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    u = User(email=f"o{i}@t.local", google_sub=f"os{i}", role=Role.OWNER)
    session.add(u)
    await session.flush()
    session.add(Store(name="내가게", category_code="butcher", owner_id=u.id, lat=37.5, lng=127.0))
    await session.commit()
    await session.refresh(u)
    return u


async def test_owner_store_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/owner/store")).status_code == 401


async def test_owner_store_forbidden_for_plain_user(client: AsyncClient, session: AsyncSession):
    u = User(email="plain@t.local", google_sub="plain", role=Role.USER)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    assert (await client.get("/api/v1/owner/store", headers=auth_headers(u))).status_code == 403


async def test_owner_sees_own_store(client: AsyncClient, session: AsyncSession):
    owner = await _owner_with_store(session, 1)
    resp = await client.get("/api/v1/owner/store", headers=auth_headers(owner))
    assert resp.status_code == 200 and resp.json()["owner_id"] == owner.id
