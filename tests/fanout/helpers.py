from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.market import Market
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.subscription import Subscription
from app.models.user import Role, User


async def seed_category(session: AsyncSession, code: str = "butcher") -> None:
    session.add(Category(code=code, name_ko="정육", sort_order=1, default_unit_code="geun"))
    await session.commit()


async def seed_sale(
    session: AsyncSession,
    *,
    lat: float = 37.58,
    lng: float = 127.04,
    category: str = "butcher",
    normal_price: int = 10000,
    sale_price: int = 5000,
    status: SaleStatus = SaleStatus.ACTIVE,
) -> Sale:
    market = Market(name="시장", lat=lat, lng=lng)
    session.add(market)
    await session.flush()
    store = Store(market_id=market.id, category_code=category, name="정육점", lat=lat, lng=lng)
    session.add(store)
    await session.flush()
    sale = Sale(
        store_id=store.id,
        category_code=category,
        title="한우 세일",
        normal_price=normal_price,
        sale_price=sale_price,
        unit_code="geun",
        total_quantity=10,
        remaining_quantity=10,
        deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
        status=status,
    )
    session.add(sale)
    await session.commit()
    await session.refresh(sale)
    return sale


async def seed_user(session: AsyncSession, i: int = 1) -> User:
    user = User(email=f"sub{i}@test.local", google_sub=f"sub-{i}", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def seed_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    lat: float = 37.58,
    lng: float = 127.04,
    categories: list[str] | None = None,
    min_discount_rate: int = 0,
    max_price: int | None = None,
    radius_m: int = 2000,
    receive_from: int = 0,
    receive_to: int = 24,
    opted_out: bool = False,
    push_enabled: bool = True,
) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        categories=categories or ["butcher"],
        lat=lat,
        lng=lng,
        min_discount_rate=min_discount_rate,
        max_price=max_price,
        radius_m=radius_m,
        receive_from=receive_from,
        receive_to=receive_to,
        opted_out=opted_out,
        push_enabled=push_enabled,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub
