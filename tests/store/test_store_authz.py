from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _user(session, i, role=Role.USER) -> User:
    # 한 테스트에서 여러 번 호출될 수 있어 카테고리 중복 삽입(PK 충돌) 방지.
    if await session.get(Category, "butcher") is None:
        session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    u = User(email=f"st{i}@t.local", google_sub=f"sts{i}", role=role)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


_BODY = {"category_code": "butcher", "name": "정육점", "lat": 37.5, "lng": 127.0}


async def test_create_store_requires_auth(client: AsyncClient, session: AsyncSession):
    await _user(session, 0)
    assert (await client.post("/api/v1/stores", json=_BODY)).status_code == 401


async def test_create_store_binds_and_promotes(client: AsyncClient, session: AsyncSession):
    user = await _user(session, 1)
    resp = await client.post("/api/v1/stores", json=_BODY, headers=auth_headers(user))
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == user.id
    await session.refresh(user)
    assert user.role == Role.OWNER  # 매장 등록 → 점주 승격


async def test_cannot_patch_others_store(client: AsyncClient, session: AsyncSession):
    owner = await _user(session, 1)
    sid = (await client.post("/api/v1/stores", json=_BODY, headers=auth_headers(owner))).json()["id"]
    attacker = await _user(session, 2)
    resp = await client.patch(f"/api/v1/stores/{sid}", json={"name": "탈취"}, headers=auth_headers(attacker))
    assert resp.status_code == 403
