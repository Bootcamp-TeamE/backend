from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _seed(session) -> int:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    store = Store(name="가게", category_code="butcher", lat=37.5, lng=127.0)
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store.id


async def _user(session, i) -> User:
    u = User(email=f"f{i}@t.local", google_sub=f"fs{i}", role=Role.USER)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_favorite_requires_auth(client: AsyncClient, session: AsyncSession):
    sid = await _seed(session)
    assert (await client.post(f"/api/v1/stores/{sid}/favorite")).status_code == 401


async def test_favorite_list_scoped_to_user(client: AsyncClient, session: AsyncSession):
    sid = await _seed(session)
    a, b = await _user(session, 1), await _user(session, 2)
    await client.post(f"/api/v1/stores/{sid}/favorite", headers=auth_headers(a))
    assert len((await client.get("/api/v1/favorites", headers=auth_headers(a))).json()) == 1
    assert (await client.get("/api/v1/favorites", headers=auth_headers(b))).json() == []
