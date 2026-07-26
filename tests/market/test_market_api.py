from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.market import Market
from app.models.store import Store


async def _seed(session: AsyncSession) -> tuple[Market, Store]:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="piece"))
    market = Market(name="테스트시장", market_type="상설장", address="서울", lat=37.5800, lng=127.0400)
    session.add(market)
    await session.commit()
    await session.refresh(market)
    store = Store(market_id=market.id, category_code="butcher", name="테스트정육", lat=37.5801, lng=127.0401)
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return market, store


async def test_search_markets_within_radius(client: AsyncClient, session: AsyncSession):
    await _seed(session)
    session.add(Market(name="먼시장", lat=35.1, lng=129.0))  # 부산
    await session.commit()

    resp = await client.get("/api/v1/markets", params={"lat": 37.58, "lng": 127.04, "radius": 1000})
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()]
    assert "테스트시장" in names
    assert "먼시장" not in names
    assert resp.json()[0]["distance_m"] is not None


async def test_market_detail_store_count(client: AsyncClient, session: AsyncSession):
    market, _ = await _seed(session)
    resp = await client.get(f"/api/v1/markets/{market.id}")
    assert resp.status_code == 200
    assert resp.json()["store_count"] == 1
    assert resp.json()["name"] == "테스트시장"


async def test_market_stores_list(client: AsyncClient, session: AsyncSession):
    market, store = await _seed(session)
    resp = await client.get(f"/api/v1/markets/{market.id}/stores")
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == [store.id]


async def test_market_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/markets/99999999")
    assert resp.status_code == 404
