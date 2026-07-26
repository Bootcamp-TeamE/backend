from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _seed_owner(session: AsyncSession, i: int = 1) -> User:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="piece"))
    user = User(email=f"owner{i}@test.local", google_sub=f"osub-{i}", role=Role.OWNER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _create_store(client: AsyncClient, owner: User, name: str = "정육점") -> dict:
    resp = await client.post("/api/v1/stores", json={
        "category_code": "butcher", "name": name, "lat": 37.5, "lng": 127.0,
    }, headers=auth_headers(owner))
    return resp


# ── POST /stores owner 바인딩 ──

async def test_create_store_binds_owner(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    resp = await _create_store(client, owner)
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == owner.id


async def test_create_store_duplicate_owner_conflict(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    assert (await _create_store(client, owner)).status_code == 201
    # 1계정=1매장 — 두 번째 등록은 거절
    dup = await _create_store(client, owner, name="둘째")
    assert dup.status_code == 409


# ── GET /owner/store ──

async def test_owner_store_found(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    created = await _create_store(client, owner)
    resp = await client.get("/api/v1/owner/store", headers=auth_headers(owner))
    assert resp.status_code == 200
    assert resp.json()["id"] == created.json()["id"]
    assert resp.json()["owner_id"] == owner.id


async def test_owner_store_not_found(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    resp = await client.get("/api/v1/owner/store", headers=auth_headers(owner))
    assert resp.status_code == 404


# ── GET /stores/{id}/sales ──

async def test_list_store_sales_active_soonest_first(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    sid = (await _create_store(client, owner)).json()["id"]
    # 마감 늦은 것 → 이른 것 순으로 등록. 응답은 마감 임박(이른) 순.
    for title, deadline in (("세일1", "2030-01-02T00:00:00Z"), ("세일2", "2030-01-01T00:00:00Z")):
        r = await client.post(f"/api/v1/stores/{sid}/sales", json={
            "title": title, "normal_price": 10000, "sale_price": 6000,
            "total_quantity": 5, "deadline_at": deadline,
        }, headers=auth_headers(owner))
        assert r.status_code == 201
    resp = await client.get(f"/api/v1/stores/{sid}/sales")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "세일2"  # 마감 임박 순(활성·미마감만)


async def test_list_store_sales_store_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/stores/99999999/sales")
    assert resp.status_code == 404


# ── PATCH /stores/{id} ──

async def test_patch_store_name(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    sid = (await _create_store(client, owner)).json()["id"]
    resp = await client.patch(
        f"/api/v1/stores/{sid}", json={"name": "수정된정육"}, headers=auth_headers(owner)
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "수정된정육"


async def test_patch_store_unknown_category(client: AsyncClient, session: AsyncSession):
    owner = await _seed_owner(session)
    sid = (await _create_store(client, owner)).json()["id"]
    resp = await client.patch(
        f"/api/v1/stores/{sid}", json={"category_code": "없음"}, headers=auth_headers(owner)
    )
    assert resp.status_code == 422


async def test_patch_store_not_found(client: AsyncClient, session: AsyncSession):
    user = await _seed_owner(session)
    resp = await client.patch(
        "/api/v1/stores/99999999", json={"name": "x"}, headers=auth_headers(user)
    )
    assert resp.status_code == 404
