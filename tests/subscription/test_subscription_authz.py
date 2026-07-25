from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _user(session, i) -> User:
    if await session.get(Category, "butcher") is None:
        session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    u = User(email=f"sub{i}@t.local", google_sub=f"subs{i}", role=Role.USER)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


_BODY = {"categories": ["butcher"], "lat": 37.5, "lng": 127.0}


async def test_subscription_requires_auth(client: AsyncClient, session: AsyncSession):
    await _user(session, 0)
    assert (await client.post("/api/v1/subscriptions", json=_BODY)).status_code == 401


async def test_subscription_scoped_to_user(client: AsyncClient, session: AsyncSession):
    a, b = await _user(session, 1), await _user(session, 2)
    await client.post("/api/v1/subscriptions", json=_BODY, headers=auth_headers(a))
    assert len((await client.get("/api/v1/subscriptions", headers=auth_headers(a))).json()) == 1
    assert (await client.get("/api/v1/subscriptions", headers=auth_headers(b))).json() == []
