from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.notification_log import NotificationLog
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import Role, User


async def seed_owner_store(session: AsyncSession, i: int = 1) -> tuple[User, Store]:
    session.add(Category(code="butcher", name_ko="정육", sort_order=1, default_unit_code="geun"))
    owner = User(email=f"owner{i}@test.local", google_sub=f"owner-{i}", role=Role.OWNER)
    session.add(owner)
    await session.flush()
    store = Store(owner_id=owner.id, category_code="butcher", name="정육점", lat=37.58, lng=127.04)
    session.add(store)
    await session.commit()
    await session.refresh(owner)
    await session.refresh(store)
    return owner, store


async def seed_buyer(session: AsyncSession, i: int = 99) -> User:
    user = User(email=f"buyer{i}@test.local", google_sub=f"buyer-{i}", role=Role.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def seed_sale(
    session: AsyncSession,
    store: Store,
    *,
    normal_price: int = 10000,
    sale_price: int = 5000,
    status: SaleStatus = SaleStatus.ACTIVE,
    deadline_hours: int = 2,
) -> Sale:
    sale = Sale(
        store_id=store.id,
        category_code=store.category_code,
        title="한우 세일",
        normal_price=normal_price,
        sale_price=sale_price,
        unit_code="geun",
        total_quantity=10,
        remaining_quantity=10,
        deadline_at=datetime.now(timezone.utc) + timedelta(hours=deadline_hours),
        status=status,
    )
    session.add(sale)
    await session.commit()
    await session.refresh(sale)
    return sale


async def seed_paid_order(session: AsyncSession, sale: Sale, user_id: int, qty: int = 1) -> Order:
    now = datetime.now(timezone.utc)
    order = Order(
        user_id=user_id,
        sale_id=sale.id,
        quantity=qty,
        total_price=qty * sale.sale_price,
        status=OrderStatus.PAID,
        reserved_at=now,
        expires_at=now + timedelta(minutes=10),
        paid_at=now,
    )
    session.add(order)
    await session.commit()
    return order


async def seed_reach(session: AsyncSession, sale: Sale, user_id: int) -> None:
    session.add(NotificationLog(sale_id=sale.id, user_id=user_id))
    await session.commit()
