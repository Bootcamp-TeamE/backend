from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _user_with_noti(session, i) -> User:
    u = User(email=f"n{i}@t.local", google_sub=f"ns{i}", role=Role.USER)
    session.add(u)
    await session.flush()
    session.add(Notification(user_id=u.id, type=NotificationType.SALE_NEARBY))
    await session.commit()
    await session.refresh(u)
    return u


async def test_list_requires_auth(client: AsyncClient):
    assert (await client.get("/api/v1/notifications")).status_code == 401


async def test_list_scoped_to_user(client: AsyncClient, session: AsyncSession):
    a = await _user_with_noti(session, 1)
    b = await _user_with_noti(session, 2)
    assert len((await client.get("/api/v1/notifications", headers=auth_headers(a))).json()) == 1
    assert len((await client.get("/api/v1/notifications", headers=auth_headers(b))).json()) == 1
