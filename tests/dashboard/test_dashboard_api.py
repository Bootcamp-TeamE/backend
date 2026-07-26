import asyncio
import json

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.events import bus
from app.models.user import Role, User
from app.routers.owner import _dashboard_events
from tests.conftest import auth_headers
from tests.dashboard.helpers import seed_buyer, seed_owner_store, seed_sale


async def test_get_dashboard(client: AsyncClient, session: AsyncSession):
    owner, store = await seed_owner_store(session)
    await seed_sale(session, store)
    resp = await client.get("/api/v1/owner/dashboard", headers=auth_headers(owner))
    assert resp.status_code == 200
    body = resp.json()
    assert body["store_id"] == store.id
    assert body["active_sales"] == 1


async def test_get_dashboard_no_store(client: AsyncClient, session: AsyncSession):
    owner = User(email="no-store@test.local", google_sub="no-store", role=Role.OWNER)
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    resp = await client.get("/api/v1/owner/dashboard", headers=auth_headers(owner))
    assert resp.status_code == 404


async def test_stream_404_when_no_store(client: AsyncClient, session: AsyncSession):
    owner = User(email="no-store-stream@test.local", google_sub="no-store-stream", role=Role.OWNER)
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    # 스트림 시작 전에 매장 확인 → 일반 GET으로도 404 확인 가능
    token = create_access_token(owner.id, owner.role.value)
    resp = await client.get("/api/v1/owner/dashboard/stream", params={"token": token})
    assert resp.status_code == 404


async def test_order_wakes_owner_bus(client: AsyncClient, session: AsyncSession):
    owner, store = await seed_owner_store(session)
    sale = await seed_sale(session, store)
    buyer = await seed_buyer(session)

    queue = bus.subscribe(bus.DASHBOARD, owner.id)
    try:
        resp = await client.post(
            "/api/v1/orders",
            json={"sale_id": sale.id, "quantity": 1},
            headers=auth_headers(buyer),
        )
        assert resp.status_code == 201
        # 주문 커밋 후 점주 채널로 깨우기 신호가 도착
        await asyncio.wait_for(queue.get(), timeout=2)
    finally:
        bus.unsubscribe(bus.DASHBOARD, owner.id, queue)


async def test_stream_initial_snapshot_then_update(session: AsyncSession, engine):
    owner, store = await seed_owner_store(session)
    await seed_sale(session, store)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    gen = _dashboard_events(owner.id, maker)
    first = await asyncio.wait_for(gen.__anext__(), timeout=3)
    assert first.startswith("data: ")
    assert json.loads(first[6:])["active_sales"] == 1

    await bus.publish(bus.DASHBOARD, owner.id)  # 구독이 걸린 상태 → 갱신 프레임
    second = await asyncio.wait_for(gen.__anext__(), timeout=3)
    assert second.startswith("data: ")

    await gen.aclose()
