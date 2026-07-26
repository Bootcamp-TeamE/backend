from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import FakePublisher
from app.models.category import Category
from app.models.market import Market
from app.models.store import Store
from app.models.user import Role, User
from tests.conftest import auth_headers
from tests.fanout.helpers import seed_category, seed_subscription, seed_user


async def _store(session: AsyncSession, lat: float = 37.58, lng: float = 127.04) -> tuple[Store, User]:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    owner = User(email="fanout-owner@test.local", google_sub="fanout-osub", role=Role.OWNER)
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


def _sale_body(**over) -> dict:
    b = {
        "title": "한우", "normal_price": 10000, "sale_price": 5000, "total_quantity": 10,
        "deadline_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }
    b.update(over)
    return b


async def test_sale_creation_publishes_sale_created(
    client: AsyncClient, session: AsyncSession, fake_publisher: FakePublisher
):
    store, owner = await _store(session)
    resp = await client.post(
        f"/api/v1/stores/{store.id}/sales", json=_sale_body(), headers=auth_headers(owner)
    )
    assert resp.status_code == 201
    sale_id = resp.json()["id"]
    assert ("sale.created", {"sale_id": sale_id}) in fake_publisher.events


async def test_reach_counts_matching_subscriptions(client: AsyncClient, session: AsyncSession):
    await seed_category(session)
    u1 = await seed_user(session, i=1)
    u2 = await seed_user(session, i=2)
    u3 = await seed_user(session, i=3)
    await seed_subscription(session, user_id=u1.id, lat=37.58, lng=127.04, categories=["butcher"])
    await seed_subscription(session, user_id=u2.id, lat=35.1, lng=129.0, categories=["butcher"])  # 부산
    await seed_subscription(session, user_id=u3.id, lat=37.58, lng=127.04, categories=["seafood"])

    resp = await client.get(
        "/api/v1/search/reach", params={"lat": 37.58, "lng": 127.04, "category": "butcher"}
    )
    assert resp.status_code == 200
    assert resp.json()["reach"] == 1  # 가까운 butcher 구독 1건만
