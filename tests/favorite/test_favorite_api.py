from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _seed(session: AsyncSession) -> tuple[User, Store]:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="piece"))
    user = User(email="fav@test.local", google_sub="fav-sub", role=Role.USER)
    session.add(user)
    store = Store(category_code="butcher", name="정육점", lat=37.5, lng=127.0)
    session.add(store)
    await session.commit()
    await session.refresh(user)
    await session.refresh(store)
    return user, store


async def test_add_favorite_then_list(client: AsyncClient, session: AsyncSession):
    user, store = await _seed(session)
    add = await client.post(f"/api/v1/stores/{store.id}/favorite", headers=auth_headers(user))
    assert add.status_code == 201

    resp = await client.get("/api/v1/favorites", headers=auth_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == store.id
    assert data[0]["name"] == "정육점"


async def test_add_favorite_idempotent(client: AsyncClient, session: AsyncSession):
    user, store = await _seed(session)
    await client.post(f"/api/v1/stores/{store.id}/favorite", headers=auth_headers(user))
    again = await client.post(f"/api/v1/stores/{store.id}/favorite", headers=auth_headers(user))
    assert again.status_code == 201  # 멱등 — 중복이어도 성공

    resp = await client.get("/api/v1/favorites", headers=auth_headers(user))
    assert len(resp.json()) == 1  # 한 번만 등록


async def test_remove_favorite(client: AsyncClient, session: AsyncSession):
    user, store = await _seed(session)
    await client.post(f"/api/v1/stores/{store.id}/favorite", headers=auth_headers(user))

    rm = await client.request(
        "DELETE", f"/api/v1/stores/{store.id}/favorite", headers=auth_headers(user)
    )
    assert rm.status_code == 204

    resp = await client.get("/api/v1/favorites", headers=auth_headers(user))
    assert resp.json() == []


async def test_remove_favorite_idempotent(client: AsyncClient, session: AsyncSession):
    user, store = await _seed(session)
    # 등록 안 한 상태에서 삭제 — 에러 없이 204
    rm = await client.request(
        "DELETE", f"/api/v1/stores/{store.id}/favorite", headers=auth_headers(user)
    )
    assert rm.status_code == 204


async def test_favorite_store_not_found(client: AsyncClient, session: AsyncSession):
    user, _ = await _seed(session)
    resp = await client.post("/api/v1/stores/99999999/favorite", headers=auth_headers(user))
    assert resp.status_code == 404


async def test_list_favorites_empty(client: AsyncClient, session: AsyncSession):
    user, _ = await _seed(session)
    resp = await client.get("/api/v1/favorites", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == []
