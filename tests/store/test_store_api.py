from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.market import Market
from app.models.store import Store


async def _seed(session: AsyncSession) -> tuple[Market, Store]:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="piece"))
    market = Market(name="시장", lat=37.5, lng=127.0)
    session.add(market)
    await session.commit()
    await session.refresh(market)
    store = Store(market_id=market.id, category_code="butcher", name="정육점", lat=37.5, lng=127.0)
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return market, store


async def test_get_store(client: AsyncClient, session: AsyncSession):
    _, store = await _seed(session)
    resp = await client.get(f"/api/v1/stores/{store.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "정육점"
    assert resp.json()["category_code"] == "butcher"


async def test_get_store_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/stores/99999999")
    assert resp.status_code == 404


async def test_create_store(client: AsyncClient, session: AsyncSession):
    market, _ = await _seed(session)
    resp = await client.post("/api/v1/stores", json={
        "category_code": "butcher", "name": "새정육", "lat": 37.5, "lng": 127.0, "market_id": market.id,
    })
    assert resp.status_code == 201
    assert resp.json()["owner_id"] is None  # 인증 없이 생성
    assert resp.json()["name"] == "새정육"


async def test_create_store_unknown_category(client: AsyncClient, session: AsyncSession):
    await _seed(session)
    resp = await client.post("/api/v1/stores", json={
        "category_code": "없음", "name": "x", "lat": 37.5, "lng": 127.0,
    })
    assert resp.status_code == 422


async def test_create_store_market_not_found(client: AsyncClient, session: AsyncSession):
    await _seed(session)
    resp = await client.post("/api/v1/stores", json={
        "category_code": "butcher", "name": "x", "lat": 37.5, "lng": 127.0, "market_id": 99999999,
    })
    assert resp.status_code == 404
