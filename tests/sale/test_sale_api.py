from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.market import Market
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers


async def _category(session: AsyncSession, code: str = "butcher", default_unit: str = "piece") -> None:
    session.add(Category(code=code, name_ko="정육", sort_order=1, default_unit_code=default_unit))
    await session.commit()


_owner_seq = 0


async def _store(session: AsyncSession, lat: float = 37.58, lng: float = 127.04) -> tuple[Store, User]:
    global _owner_seq
    _owner_seq += 1
    owner = User(email=f"owner{_owner_seq}@test.local", google_sub=f"osub-{_owner_seq}", role=Role.OWNER)
    session.add(owner)
    await session.flush()
    market = Market(name="시장", lat=lat, lng=lng)
    session.add(market)
    await session.flush()
    store = Store(market_id=market.id, owner_id=owner.id, category_code="butcher", name="정육점", lat=lat, lng=lng)
    session.add(store)
    await session.commit()
    await session.refresh(store)
    await session.refresh(owner)
    return store, owner


def _body(**over) -> dict:
    b = {
        "title": "한우 8팩", "normal_price": 4000, "sale_price": 2000, "total_quantity": 8,
        "deadline_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }
    b.update(over)
    return b


async def test_create_sale(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["remaining_quantity"] == 8
    assert body["status"] == "active"
    assert body["unit_code"] == "piece"
    assert body["category_code"] == "butcher"  # 매장 카테고리 상속
    assert body["discount_rate"] == 50


async def test_create_sale_with_description_and_image(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales",
        json=_body(description="신선한 한우입니다", image_url="/uploads/abc.jpg"),
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "신선한 한우입니다"
    assert body["image_url"] == "/uploads/abc.jpg"


async def test_create_sale_without_description_and_image(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] is None
    assert body["image_url"] is None


async def test_create_sale_bad_prices(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales",
        json=_body(normal_price=2000, sale_price=3000),
        headers=auth_headers(owner),
    )
    assert resp.status_code == 422


async def test_create_sale_store_not_found(client: AsyncClient, session: AsyncSession):
    await _category(session)
    owner = User(email="owner-nf@test.local", google_sub="osub-nf", role=Role.OWNER)
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    resp = await client.post(
        "/api/v1/stores/99999999/sales", json=_body(), headers=auth_headers(owner)
    )
    assert resp.status_code == 404


async def test_get_sale(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    sale_id = (
        await client.post(
            f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
        )
    ).json()["id"]
    resp = await client.get(f"/api/v1/sales/{sale_id}")
    assert resp.status_code == 200
    assert resp.json()["discount_rate"] == 50


async def test_list_sales_active_only(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(title="지금세일"), headers=auth_headers(owner)
    )
    await client.post(
        f"/api/v1/stores/{store.id}/sales",
        json=_body(title="지난세일", deadline_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()),
        headers=auth_headers(owner),
    )
    resp = await client.get("/api/v1/sales")
    titles = [s["title"] for s in resp.json()]
    assert "지금세일" in titles
    assert "지난세일" not in titles


async def test_close_sale(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    sale_id = (
        await client.post(
            f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
        )
    ).json()["id"]
    resp = await client.patch(
        f"/api/v1/sales/{sale_id}", json={"status": "closed"}, headers=auth_headers(owner)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
    listed = await client.get("/api/v1/sales")
    assert sale_id not in [s["id"] for s in listed.json()]


async def test_search_sales_within_radius(client: AsyncClient, session: AsyncSession):
    await _category(session)
    near, near_owner = await _store(session, lat=37.58, lng=127.04)
    far, far_owner = await _store(session, lat=35.1, lng=129.0)  # 부산
    await client.post(
        f"/api/v1/stores/{near.id}/sales", json=_body(title="가까운세일"), headers=auth_headers(near_owner)
    )
    await client.post(
        f"/api/v1/stores/{far.id}/sales", json=_body(title="먼세일"), headers=auth_headers(far_owner)
    )
    resp = await client.get("/api/v1/search/sales", params={"lat": 37.58, "lng": 127.04, "radius": 1000})
    titles = [s["title"] for s in resp.json()]
    assert "가까운세일" in titles
    assert "먼세일" not in titles


async def test_update_sale_price(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    sale_id = (
        await client.post(
            f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
        )
    ).json()["id"]
    resp = await client.patch(
        f"/api/v1/sales/{sale_id}", json={"sale_price": 1000}, headers=auth_headers(owner)
    )
    assert resp.status_code == 200
    assert resp.json()["sale_price"] == 1000
    assert resp.json()["discount_rate"] == 75  # (4000-1000)/4000, 추가 할인 반영


async def test_update_sale_price_invalid(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    sale_id = (
        await client.post(
            f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
        )
    ).json()["id"]
    resp = await client.patch(
        f"/api/v1/sales/{sale_id}", json={"sale_price": 5000}, headers=auth_headers(owner)
    )  # >= 정상가 4000
    assert resp.status_code == 422


async def test_create_weight_sale(client: AsyncClient, session: AsyncSession):
    await _category(session)
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales",
        json=_body(title="삼겹살", unit_code="g", min_order=100, total_quantity=5000, normal_price=2500, sale_price=1500),
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201
    assert resp.json()["unit_code"] == "g"
    assert resp.json()["min_order"] == 100


async def test_unit_inherits_category_default(client: AsyncClient, session: AsyncSession):
    await _category(session, default_unit="geun")
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_body(), headers=auth_headers(owner)
    )
    assert resp.status_code == 201
    assert resp.json()["unit_code"] == "geun"  # unit 미지정 → 카테고리 기본단위 상속


async def test_get_units(client: AsyncClient):
    resp = await client.get("/api/v1/units")
    assert resp.status_code == 200
    codes = [u["code"] for u in resp.json()]
    assert "piece" in codes and "geun" in codes
