"""특정 이메일 계정을 점주(OWNER)로 승격 + 매장 생성 + 가벼운 활동 시드. 멱등.

용도: 배포에서 "익명 데모 점주 버튼" 없이, 내 실제 구글 계정을 점주로 쓰고 싶을 때.
UI에는 셀프 온보딩(매장 등록) 경로가 없으므로(매장 등록 화면이 점주 전용) 이 스크립트로 승격한다.

순서(중요):
  1) 배포 앱에서 그 이메일 계정으로 구글 로그인을 먼저 한다(계정 행이 생성됨).
     - 먼저 로그인해야 하는 이유: /auth/google 은 google_sub 로 유저를 찾는데,
       같은 이메일이 다른 sub 로 이미 있으면 409 로 로그인이 막힌다. 그러니 로그인 먼저.
  2) 이 스크립트 실행:
       PYTHONPATH=. ./.venv-app/bin/python seed/promote_owner.py you@example.com
     (또는 OWNER_EMAIL 환경변수)
  3) .env 에서 VITE_DEV_LOGIN=false, DEV_LOGIN=0 → 데모 점주 버튼/엔드포인트 비활성화.

멱등: 이미 점주+매장+세일이면 다시 만들지 않는다. 역할 승격만 항상 보장.
매장 이름/카테고리/위치/세일 목록은 아래 상수로, 이후 점주 화면에서 수정 가능.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.models.category import Category
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import Role, User

# 생성할 매장 기본값(이후 점주 화면에서 수정 가능)
STORE_NAME = "우리 청과"
STORE_CATEGORY = "greengrocer"  # 청과
STORE_LAT = 37.5665
STORE_LNG = 126.9780  # 서울시청 인근

# 주문을 붙일 시드 구매자(로그인용 아님 — 시드 데이터 소유자일 뿐)
SEED_BUYER_EMAIL = "seed-buyer@solde.demo"

# (title, normal_price, sale_price, total_quantity)
SALE_ITEMS = [
    ("상추 한 봉지", 3000, 2000, 10),
    ("방울토마토 500g", 6000, 3900, 8),
    ("애호박 2개", 3000, 1900, 12),
]


async def main() -> None:
    email = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OWNER_EMAIL", "")).strip()
    if not email:
        print("사용법: promote_owner.py <이메일>  (또는 OWNER_EMAIL 환경변수)")
        return

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"'{email}' 계정을 찾을 수 없습니다. 배포 앱에서 그 계정으로 구글 로그인을 먼저 하세요.")
            await engine.dispose()
            return

        # 항상 점주로 승격(멱등)
        user.role = Role.OWNER

        # 소유 매장 확보(없으면 생성)
        store = (
            await session.execute(
                select(Store).where(Store.owner_id == user.id, Store.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        created_store = False
        if store is None:
            category = await session.get(Category, STORE_CATEGORY)
            if category is None:
                print(f"카테고리 '{STORE_CATEGORY}' 가 없습니다. 먼저 매장/업종 시드(load_seed)를 실행하세요.")
                await engine.dispose()
                return
            store = Store(
                owner_id=user.id,
                category_code=STORE_CATEGORY,
                name=STORE_NAME,
                lat=STORE_LAT,
                lng=STORE_LNG,
            )
            session.add(store)
            await session.flush()
            created_store = True

        # 활동 시드 — 매장에 세일이 이미 있으면 건너뜀(멱등)
        has_sale = (
            await session.execute(
                select(Sale.id).where(Sale.store_id == store.id, Sale.is_deleted.is_(False)).limit(1)
            )
        ).scalar_one_or_none()

        seeded = ""
        if has_sale is None:
            category = await session.get(Category, store.category_code)
            unit_code = category.default_unit_code
            now = datetime.now(timezone.utc)

            buyer = (
                await session.execute(select(User).where(User.email == SEED_BUYER_EMAIL))
            ).scalar_one_or_none()
            if buyer is None:
                buyer = User(
                    email=SEED_BUYER_EMAIL,
                    google_sub=f"seed:{SEED_BUYER_EMAIL}",
                    name="시드구매자",
                    role=Role.USER,
                )
                session.add(buyer)
                await session.flush()

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

            # 오늘 결제 주문(대시보드 오늘 주문·매출 채움): PAID 2 + PICKED_UP 1
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
            revenue = sum(o.total_price for o in created_orders)
            seeded = f", 세일 {len(sales)}건 + 결제주문 {len(created_orders)}건(매출 {revenue}원)"

        await session.commit()
        store_note = "매장 생성" if created_store else f"기존 매장 유지(id={store.id})"
        print(f"'{email}' → 점주 승격 완료. {store_note}: {store.name}{seeded}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
