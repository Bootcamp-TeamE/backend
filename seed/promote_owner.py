"""특정 이메일 계정을 점주(OWNER)로 승격 + 시흥삼미시장의 기존 매장 점주로 교체 + 활동 시드. 멱등.

용도: 배포에서 "익명 데모 점주 버튼" 없이, 내 실제 구글 계정을 점주로 쓰고 싶을 때.
UI에 셀프 온보딩(매장 등록)이 없으므로(매장 등록 화면이 점주 전용) 이 스크립트로 승격한다.

매장은 새로 만들지 않고, 시흥삼미시장(구매자 홈 기본 위치)의 청과 매장 중 하나
— 기존 점주가 목데이터(@mock.local)이고 세일이 없는 매장 — 의 점주만 이 계정으로 교체한다.
그러면 실제 시장 매장 이름·위치를 그대로 쓰면서 구매자 홈 반경 검색에도 바로 뜬다.

활동 주문은 PICKED_UP(픽업완료)로 시드한다 — PAID로 두면 노쇼 환불 워커가 30분 뒤 환불해
대시보드 숫자가 사라지므로, 안정적으로 유지되도록 픽업완료로 넣는다.

순서(중요):
  1) 배포 앱에서 그 이메일 계정으로 구글 로그인을 먼저 한다(계정 행이 생성됨).
     - /auth/google 은 google_sub 로 유저를 찾고, 같은 이메일이 다른 sub 로 이미 있으면 409 로 막힌다.
  2) 실행: PYTHONPATH=. ./.venv-app/bin/python seed/promote_owner.py you@example.com
     (또는 OWNER_EMAIL 환경변수)
  3) .env 에서 VITE_DEV_LOGIN=false, DEV_LOGIN=0 → 데모 점주 버튼/엔드포인트 비활성화.

멱등: 이미 매장을 소유한 계정이면 교체하지 않는다(역할 승격만 보장).
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

import app.models  # noqa: F401  모델 등록
from app.database import AsyncSessionLocal, engine
from app.models.category import Category
from app.models.market import Market
from app.models.order import Order, OrderStatus
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.user import Role, User

MARKET_NAME = "시흥삼미시장"
STORE_CATEGORY = "butcher"  # 정육 (수산으로 바꾸려면 "seafood" + 아래 SALE_ITEMS 교체)
MOCK_OWNER_SUFFIX = "@mock.local"  # 교체 가능한(목데이터) 점주 판별
SKIP_NAME_TOKENS = ("상인회", "조합", "연합")  # 실제 점포가 아닌 단체명은 건너뜀

SEED_BUYER_EMAIL = "seed-buyer@solde.demo"

# (title, normal_price, sale_price, total_quantity) — STORE_CATEGORY 에 맞춘 품목
SALE_ITEMS = [
    ("삼겹살 500g", 15000, 9900, 10),
    ("목살 500g", 13000, 8900, 8),
    ("한우 국거리 300g", 20000, 13900, 6),
]


async def _pick_takeover_store(session, market_id: int) -> Store | None:
    """시흥삼미시장의 청과 매장 중, 세일이 없고 점주가 목데이터인(또는 주인 없는) 매장 하나."""
    candidates = (
        await session.execute(
            select(Store)
            .where(
                Store.market_id == market_id,
                Store.category_code == STORE_CATEGORY,
                Store.is_deleted.is_(False),
            )
            .order_by(Store.id)
        )
    ).scalars().all()
    for store in candidates:
        if any(tok in store.name for tok in SKIP_NAME_TOKENS):
            continue
        has_sale = (
            await session.execute(
                select(func.count()).select_from(Sale).where(
                    Sale.store_id == store.id, Sale.is_deleted.is_(False)
                )
            )
        ).scalar()
        if has_sale:
            continue
        if store.owner_id is None:
            return store
        owner = await session.get(User, store.owner_id)
        if owner is not None and owner.email.endswith(MOCK_OWNER_SUFFIX):
            return store
    return None


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

        user.role = Role.OWNER  # 항상 점주로 승격(멱등)

        store = (
            await session.execute(
                select(Store).where(Store.owner_id == user.id, Store.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        took_over = False
        prev_owner = ""
        if store is None:
            market = (
                await session.execute(select(Market).where(Market.name == MARKET_NAME))
            ).scalar_one_or_none()
            if market is None:
                print(f"'{MARKET_NAME}' 시장이 없습니다. 먼저 매장/시장 시드(load_seed)를 실행하세요.")
                await engine.dispose()
                return
            store = await _pick_takeover_store(session, market.id)
            if store is None:
                print(f"'{MARKET_NAME}'에서 점주를 교체할 청과 매장을 찾지 못했습니다.")
                await engine.dispose()
                return
            if store.owner_id is not None:
                displaced = await session.get(User, store.owner_id)
                prev_owner = displaced.email if displaced else str(store.owner_id)
            store.owner_id = user.id
            took_over = True

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

            # 오늘 활동: 모두 PICKED_UP(픽업완료) — 노쇼 환불 대상이 아니라 대시보드에 계속 남는다.
            created_orders: list[Order] = []
            for sale, quantity in [(sales[0], 2), (sales[1], 1), (sales[2], 1)]:
                order = Order(
                    user_id=buyer.id,
                    sale_id=sale.id,
                    quantity=quantity,
                    total_price=quantity * sale.sale_price,
                    status=OrderStatus.PICKED_UP,
                    qr_token=uuid.uuid4().hex,
                    reserved_at=now,
                    expires_at=now + timedelta(minutes=30),
                    paid_at=now,
                    picked_up_at=now,
                )
                session.add(order)
                sale.remaining_quantity -= quantity
                created_orders.append(order)
            await session.flush()
            for order in created_orders:
                order.pickup_no = f"{order.id:06d}"
            revenue = sum(o.total_price for o in created_orders)
            seeded = f", 세일 {len(sales)}건 + 픽업완료 주문 {len(created_orders)}건(매출 {revenue}원)"

        await session.commit()
        if took_over:
            note = f"'{store.name}'(id={store.id}, {MARKET_NAME}) 점주 교체"
            if prev_owner:
                note += f" (기존 점주 {prev_owner} → 해제)"
        else:
            note = f"기존 매장 유지(id={store.id}): {store.name}"
        print(f"'{email}' → 점주 승격 완료. {note}{seeded}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
