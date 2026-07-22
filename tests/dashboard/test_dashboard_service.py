from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sale import SaleStatus
from app.models.user import Role, User
from app.services.dashboard import compute_dashboard
from tests.dashboard.helpers import (
    seed_buyer,
    seed_owner_store,
    seed_paid_order,
    seed_reach,
    seed_sale,
)


async def test_dashboard_snapshot_metrics(client, session: AsyncSession):
    owner, store = await seed_owner_store(session)
    sale = await seed_sale(session, store)
    buyer = await seed_buyer(session)
    await seed_paid_order(session, sale, buyer.id, qty=2)  # 판매액 2*5000=10000
    await seed_reach(session, sale, buyer.id)

    data = await compute_dashboard(session, owner.id)
    assert data is not None
    assert data["store_id"] == store.id
    assert data["active_sales"] == 1
    assert data["today_orders"] == 1
    assert data["today_revenue"] == 10000
    assert data["total_reach"] == 1


async def test_dashboard_excludes_inactive_sale_and_unpaid(client, session: AsyncSession):
    owner, store = await seed_owner_store(session)
    await seed_sale(session, store, status=SaleStatus.CLOSED)  # 비활성 → active 카운트 제외
    active = await seed_sale(session, store)
    buyer = await seed_buyer(session)
    # 결제 없음 → today_orders 0

    data = await compute_dashboard(session, owner.id)
    assert data["active_sales"] == 1  # active 1건만
    assert data["today_orders"] == 0
    assert data["today_revenue"] == 0
    assert data["total_reach"] == 0


async def test_dashboard_owner_without_store(client, session: AsyncSession):
    owner = User(email="noshop@test.local", google_sub="noshop", role=Role.OWNER)
    session.add(owner)
    await session.commit()
    await session.refresh(owner)

    assert await compute_dashboard(session, owner.id) is None
