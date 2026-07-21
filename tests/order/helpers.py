from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.market import Market
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import Role, User


async def seed_sale(
    session: AsyncSession,
    *,
    remaining: int = 5,
    sale_price: int = 2000,
    min_order: int = 1,
    status: SaleStatus = SaleStatus.ACTIVE,
    deadline_hours: int = 2,
) -> Sale:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="piece"))
    market = Market(name="시장", lat=37.58, lng=127.04)
    session.add(market)
    await session.flush()
    store = Store(market_id=market.id, category_code="butcher", name="정육점", lat=37.58, lng=127.04)
    session.add(store)
    await session.flush()
    sale = Sale(
        store_id=store.id,
        category_code="butcher",
        title="한우 세일",
        normal_price=4000,
        sale_price=sale_price,
        unit_code="piece",
        min_order=min_order,
        total_quantity=remaining,
        remaining_quantity=remaining,
        deadline_at=datetime.now(timezone.utc) + timedelta(hours=deadline_hours),
        status=status,
    )
    session.add(sale)
    await session.commit()
    await session.refresh(sale)
    return sale


async def seed_user(session: AsyncSession, i: int = 1) -> User:
    user = User(email=f"buyer{i}@test.local", google_sub=f"sub-{i}", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
