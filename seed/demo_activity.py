"""데모 점주 매장 활동 시드 — 세일 + (결제) 주문. 멱등.

`owner@solde.demo` 점주의 매장에 ACTIVE 세일 몇 건과, `buyer@solde.demo` 구매자의
결제 완료 주문을 채워 점주 대시보드(compute_dashboard)가 0이 아니게 만든다.
이미 세일이 있으면(재실행) 아무것도 하지 않는다.

전제: seed/demo_users.py 로 데모 유저·매장 귀속이 끝나 있어야 한다.

실행: backend/ 에서
    PYTHONPATH=. ./.venv-app/bin/python seed/demo_activity.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.models.category import Category
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import User

DEMO_OWNER_EMAIL = "owner@solde.demo"
DEMO_BUYER_EMAIL = "buyer@solde.demo"

# (title, normal_price, sale_price, total_quantity)
SALE_ITEMS = [
    ("소금빵", 5000, 3500, 10),
    ("크로와상", 12000, 7900, 10),
    ("단팥빵", 3000, 2000, 10),
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        owner = (
            await session.execute(select(User).where(User.email == DEMO_OWNER_EMAIL))
        ).scalar_one_or_none()
        buyer = (
            await session.execute(select(User).where(User.email == DEMO_BUYER_EMAIL))
        ).scalar_one_or_none()
        if owner is None or buyer is None:
            print("데모 유저가 없습니다. 먼저 seed/demo_users.py 를 실행하세요.")
            await engine.dispose()
            return

        store = (
            await session.execute(
                select(Store).where(Store.owner_id == owner.id, Store.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if store is None:
            print("데모 점주에게 귀속된 매장이 없습니다. 먼저 seed/demo_users.py 를 실행하세요.")
            await engine.dispose()
            return

        existing = (
            await session.execute(
                select(Sale.id).where(Sale.store_id == store.id, Sale.is_deleted.is_(False)).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"이미 시드됨: store_id={store.id} 에 세일이 존재합니다.")
            await engine.dispose()
            return

        category = (
            await session.execute(select(Category).where(Category.code == store.category_code))
        ).scalar_one_or_none()
        if category is None:
            print(f"카테고리를 찾을 수 없습니다: {store.category_code}")
            await engine.dispose()
            return
        unit_code = category.default_unit_code

        now = datetime.now(timezone.utc)

        sales: list[Sale] = []
        for i, (title, normal_price, sale_price, total_quantity) in enumerate(SALE_ITEMS):
            sale = Sale(
                store_id=store.id,
                category_code=store.category_code,
                title=title,
                normal_price=normal_price,
                sale_price=sale_price,
                unit_code=unit_code,
                min_order=1,
                total_quantity=total_quantity,
                remaining_quantity=total_quantity,
                deadline_at=now + timedelta(hours=2 + i * 0.5),
                status=SaleStatus.ACTIVE,
            )
            session.add(sale)
            sales.append(sale)
        await session.flush()

        # 주문 2건 PAID + 1건 PICKED_UP (모두 오늘, paid_at=now)
        orders_spec = [
            (sales[0], 2, OrderStatus.PAID),
            (sales[1], 1, OrderStatus.PAID),
            (sales[2], 1, OrderStatus.PICKED_UP),
        ]

        created_orders: list[Order] = []
        for sale, quantity, status in orders_spec:
            order = Order(
                user_id=buyer.id,
                sale_id=sale.id,
                quantity=quantity,
                total_price=quantity * sale.sale_price,
                status=status,
                qr_token=uuid.uuid4().hex,
                reserved_at=now,
                expires_at=now + timedelta(minutes=30),
                paid_at=now,
                picked_up_at=now if status == OrderStatus.PICKED_UP else None,
            )
            session.add(order)
            sale.remaining_quantity -= quantity
            created_orders.append(order)
        await session.flush()

        for order in created_orders:
            order.pickup_no = f"{order.id:06d}"

        await session.commit()

        paid_count = sum(1 for _, _, s in orders_spec if s in (OrderStatus.PAID, OrderStatus.PICKED_UP))
        today_revenue = sum(o.total_price for o in created_orders)
        print(
            f"데모 활동 시드 완료: store_id={store.id}, sales={len(sales)}건, "
            f"paid_orders={paid_count}건, today_revenue={today_revenue}원"
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
