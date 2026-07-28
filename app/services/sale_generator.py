"""데모용 마감세일 생성·재생성 로직.

정책(요구사항):
- 서울에 데이터가 쏠려 있어(≈96%) 지역별 비율로 매장을 뽑는다: 서울 20%, 시흥 40%.
  각 지역 안에서도 시장별 라운드로빈으로 골고루 뽑아 특정 시장 쏠림을 막는다.
- 뽑힌 매장마다 2~5개의 세일을 만든다(품목명은 카테고리별 상품 풀에서 중복 없이).
- 한 매장의 상품은 마감시각을 공유한다(매장당 마감시각 1개).
- 정상가 = 카테고리 대표 평균가 × 랜덤(0.8~1.2), 100원 단위 반올림.
- 할인율 = 랜덤 30~50%. 판매가 = 정상가 × (1-할인율), 100원 단위(유효 할인율 30~50% 클램프).
- 마감시각 = now + 랜덤(1~3시간, 10분 단위).
- 마감이 지난 세일은 정상가·할인율·마감시각·이미지를 재생성해 UPDATE하고, 재고·상태를 되살린다.
- 상품별 이미지는 Wikimedia Commons에서 라벨 검증해 고른 정확한 사진 URL을 붙인다.

CATEGORY_AVG_PRICE는 전통시장 품목의 대표 평균가 추정치(고정 테이블)이며 실시간
시세가 아니다. 값만 바꾸면 가격대 전체가 조정된다.
"""

import math
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.market import Market
from app.models.sale import Sale, SaleStatus
from app.models.store import Store

# 카테고리별 대표 평균가(원). 단위는 카테고리 기본 단위 기준(예: 정육=근, 수산=kg).
CATEGORY_AVG_PRICE: dict[str, int] = {
    "butcher": 18000,
    "seafood": 15000,
    "greengrocer": 8000,
    "sidedish": 6000,
    "ricecake": 9000,
    "tofu_namul": 3500,
    "egg_dairy": 7000,
    "streetfood": 4000,
    "flower": 20000,
}
DEFAULT_AVG = 8000

# 카테고리별 상품 풀(각 5종). 정확한 이미지를 붙일 수 있는 대표 품목으로 추렸다.
CATEGORY_ITEMS: dict[str, list[str]] = {
    "butcher": ["삼겹살", "목살", "등심", "불고기", "닭다리살"],
    "seafood": ["고등어", "갈치", "오징어", "새우", "조개"],
    "greengrocer": ["사과", "감귤", "딸기", "대파", "토마토"],
    "sidedish": ["배추김치", "잡채", "계란말이", "멸치볶음", "콩자반"],
    "ricecake": ["가래떡", "인절미", "송편", "백설기", "꿀떡"],
    "tofu_namul": ["손두부", "콩나물", "숙주나물", "도토리묵", "미나리"],
    "egg_dairy": ["계란", "우유", "치즈", "버터", "요구르트"],
    "streetfood": ["김밥", "떡볶이", "순대", "손만두", "호떡"],
    "flower": ["장미", "튤립", "국화", "해바라기", "카네이션"],
}
DEFAULT_ITEMS = ["오늘의 특가"]

# 상품별 이미지: Wikimedia Commons에서 라벨 검증해 고른 사진을 로컬로 내려받아 /uploads로 서빙.
# 외부 핫링크(레이트리밋·차단) 대신 자체 호스팅 → 안정적. 파일은 seed/download_product_images.py로 받는다.
# title: (저장 파일명, Commons 원본 URL)
PRODUCT_IMAGE_DIR = "products"
_C = "https://upload.wikimedia.org/wikipedia/commons"
PRODUCT_IMAGE_SOURCES: dict[str, tuple[str, str]] = {
    "삼겹살": ("samgyeopsal.jpg", f"{_C}/thumb/e/e1/Korean.cuisine-Samgyeopsal-01.jpg/500px-Korean.cuisine-Samgyeopsal-01.jpg"),
    "목살": ("pork_neck.jpg", f"{_C}/thumb/7/7c/Pork_neck_meat_with_salad.jpg/500px-Pork_neck_meat_with_salad.jpg"),
    "등심": ("beef_sirloin.jpeg", "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/%EB%8C%80%ED%86%B5%EB%A0%B9%EC%83%81%EC%97%90_%EB%B9%9B%EB%82%98%EB%8A%94_%ED%96%89%EC%A3%BC%ED%95%9C%EC%9A%B0.jpg/960px-%EB%8C%80%ED%86%B5%EB%A0%B9%EC%83%81%EC%97%90_%EB%B9%9B%EB%82%98%EB%8A%94_%ED%96%89%EC%A3%BC%ED%95%9C%EC%9A%B0.jpg"),
    # promote_owner 정육 데모 품목. 한우 국거리는 한우(등심) 이미지 재사용.
    "한우 국거리": ("beef_sirloin.jpeg", "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/%EB%8C%80%ED%86%B5%EB%A0%B9%EC%83%81%EC%97%90_%EB%B9%9B%EB%82%98%EB%8A%94_%ED%96%89%EC%A3%BC%ED%95%9C%EC%9A%B0.jpg/960px-%EB%8C%80%ED%86%B5%EB%A0%B9%EC%83%81%EC%97%90_%EB%B9%9B%EB%82%98%EB%8A%94_%ED%96%89%EC%A3%BC%ED%95%9C%EC%9A%B0.jpg"),
    "불고기": ("bulgogi.jpg", f"{_C}/thumb/7/76/Bulgogi_3.jpg/500px-Bulgogi_3.jpg"),
    "닭다리살": ("chicken_drumstick.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/HK_food_raw_chicken_legs_February_2020_SS2_01.jpg/960px-HK_food_raw_chicken_legs_February_2020_SS2_01.jpg"),
    "고등어": ("mackerel.jpg", f"{_C}/thumb/8/88/Maquereaux_etal.jpg/500px-Maquereaux_etal.jpg"),
    "갈치": ("hairtail.jpg", f"{_C}/thumb/7/75/Trichiurus_lepturus_by_OpenCage.jpg/500px-Trichiurus_lepturus_by_OpenCage.jpg"),
    "오징어": ("squid.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Squid_caught_by_local_fishermen_from_Pamboang_Village.jpg/960px-Squid_caught_by_local_fishermen_from_Pamboang_Village.jpg"),
    "새우": ("shrimp.jpg", f"{_C}/thumb/c/c2/Raw_shrimp.jpg/500px-Raw_shrimp.jpg"),
    "조개": ("clam.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/The_vibrant_shellfish_and_seaweed_stall_at_Toledo_City_Public_Market.jpg/960px-The_vibrant_shellfish_and_seaweed_stall_at_Toledo_City_Public_Market.jpg"),
    "사과": ("apple.jpg", f"{_C}/thumb/1/15/Red_Apple.jpg/500px-Red_Apple.jpg"),
    "감귤": ("tangerine.jpg", f"{_C}/thumb/4/49/Mandarin_Oranges_%28Citrus_Reticulata%29.jpg/500px-Mandarin_Oranges_%28Citrus_Reticulata%29.jpg"),
    "딸기": ("strawberry.jpg", f"{_C}/d/de/FraiseFruitPhoto.jpg"),
    "대파": ("scallion.jpg", f"{_C}/thumb/7/70/2010-10-16_Scallions_in_Taipei.jpg/500px-2010-10-16_Scallions_in_Taipei.jpg"),
    "토마토": ("tomato.jpg", f"{_C}/thumb/8/88/Bright_red_tomato_and_cross_section02.jpg/500px-Bright_red_tomato_and_cross_section02.jpg"),
    "배추김치": ("kimchi.jpg", f"{_C}/thumb/e/e1/Korean_Kimchi.jpg/500px-Korean_Kimchi.jpg"),
    "잡채": ("japchae.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Japchae%2C_Noodles_with_Sauteed_Vegetables.jpg/960px-Japchae%2C_Noodles_with_Sauteed_Vegetables.jpg"),
    "계란말이": ("gyeranmari.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d8/Gyeran-mari_1.jpg/960px-Gyeran-mari_1.jpg"),
    "멸치볶음": ("myeolchi.jpg", f"{_C}/thumb/5/55/Myeolchi-bokkeum_2.jpg/500px-Myeolchi-bokkeum_2.jpg"),
    "콩자반": ("kongjaban.jpg", f"{_C}/thumb/9/9f/Kongjaban_%28savoury_soybean%29.jpg/500px-Kongjaban_%28savoury_soybean%29.jpg"),
    "가래떡": ("garaetteok.jpg", f"{_C}/thumb/6/65/Garae-tteok.jpg/500px-Garae-tteok.jpg"),
    "인절미": ("injeolmi.jpg", f"{_C}/thumb/8/8b/Injeolmi_%28tteok%29_%28rice_cake%29.jpg/500px-Injeolmi_%28tteok%29_%28rice_cake%29.jpg"),
    "송편": ("songpyeon.jpg", f"{_C}/thumb/f/fa/KOCIS_songpyeon_%284994899563%29.jpg/500px-KOCIS_songpyeon_%284994899563%29.jpg"),
    "백설기": ("baekseolgi.jpg", "https://upload.wikimedia.org/wikipedia/commons/d/d1/Steamed_Rice_Cake.JPG"),
    "꿀떡": ("kkultteok.jpg", f"{_C}/thumb/4/43/Korean.dessert-Tteok-Songpyeon-Kkultteok.01.jpg/500px-Korean.dessert-Tteok-Songpyeon-Kkultteok.01.jpg"),
    "손두부": ("tofu.jpg", f"{_C}/thumb/5/5b/Milk_tofu.JPG/500px-Milk_tofu.JPG"),
    "콩나물": ("kongnamul.jpg", f"{_C}/thumb/4/4f/Kongnamul_%28soybean_sprout%29_2.jpg/500px-Kongnamul_%28soybean_sprout%29_2.jpg"),
    "숙주나물": ("sukju.jpg", f"{_C}/thumb/f/fe/Mung_bean_sprouts%2C_close-up.jpg/500px-Mung_bean_sprouts%2C_close-up.jpg"),
    "도토리묵": ("dotorimuk.jpg", f"{_C}/thumb/8/87/Korean_acorn_jelly-Dotorimuk-02.jpg/500px-Korean_acorn_jelly-Dotorimuk-02.jpg"),
    "미나리": ("minari.jpg", f"{_C}/thumb/a/a0/Oenanthe_javanica1.jpg/500px-Oenanthe_javanica1.jpg"),
    "계란": ("egg.jpg", f"{_C}/thumb/8/83/Egg_cartons_with_chicken_eggs_03.jpg/500px-Egg_cartons_with_chicken_eggs_03.jpg"),
    "우유": ("milk.jpg", f"{_C}/thumb/8/80/Bowl_milk_glass.jpg/500px-Bowl_milk_glass.jpg"),
    "치즈": ("cheese.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0d/White_cheddar_cheese_sliced_CNE.jpg/960px-White_cheddar_cheese_sliced_CNE.jpg"),
    "버터": ("butter.jpg", "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f4/Butter_dish.jpg/960px-Butter_dish.jpg"),
    "요구르트": ("yogurt.jpg", f"{_C}/thumb/b/b8/Joghurt.jpg/500px-Joghurt.jpg"),
    "김밥": ("gimbap.jpg", f"{_C}/thumb/0/0e/Gimbap_%28pixabay%29.jpg/500px-Gimbap_%28pixabay%29.jpg"),
    "떡볶이": ("tteokbokki.jpg", f"{_C}/thumb/5/56/Korean.snacks-Tteokbokki-08.jpg/500px-Korean.snacks-Tteokbokki-08.jpg"),
    "순대": ("sundae.jpg", f"{_C}/thumb/4/42/Korean.food-Sundae-01.jpg/500px-Korean.food-Sundae-01.jpg"),
    "손만두": ("mandu.jpg", f"{_C}/thumb/1/1a/Pan_dumplings.jpg/500px-Pan_dumplings.jpg"),
    "호떡": ("hotteok.jpg", f"{_C}/thumb/9/94/Korean_snack-Hotteok-01.jpg/500px-Korean_snack-Hotteok-01.jpg"),
    "장미": ("rose.jpg", f"{_C}/thumb/d/d7/Red_rose_with_black_background.jpg/500px-Red_rose_with_black_background.jpg"),
    "튤립": ("tulip.jpg", f"{_C}/thumb/3/3c/Red_and_white_tulip_at_Myddelton_House%2C_Enfield%2C_London.jpg/500px-Red_and_white_tulip_at_Myddelton_House%2C_Enfield%2C_London.jpg"),
    "국화": ("chrysanthemum.png", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Chrysanthemum_November_2015_Sochi.JPG/960px-Chrysanthemum_November_2015_Sochi.JPG"),
    "해바라기": ("sunflower.jpg", f"{_C}/thumb/4/40/Sunflower_sky_backdrop.jpg/500px-Sunflower_sky_backdrop.jpg"),
    "카네이션": ("carnation.jpg", f"{_C}/thumb/4/44/Rose_and_carnation_flower_bouquet_01.jpg/500px-Rose_and_carnation_flower_bouquet_01.jpg"),
}
PRODUCT_IMAGES: dict[str, str] = {
    title: f"/uploads/{PRODUCT_IMAGE_DIR}/{fname}" for title, (fname, _) in PRODUCT_IMAGE_SOURCES.items()
}


def image_url_for(title: str) -> str | None:
    url = PRODUCT_IMAGES.get(title)
    if url:
        return url
    for key, mapped in PRODUCT_IMAGES.items():
        if title.startswith(key):
            return mapped
    return None


DISCOUNT_MIN, DISCOUNT_MAX = 0.30, 0.50
PRICE_JITTER = 0.20
DEADLINE_CHOICES = list(range(60, 181, 10))  # 60,70,…,180분
PER_STORE_MIN, PER_STORE_MAX = 2, 5
STOCK_MIN, STOCK_MAX = 3, 12
SEOUL_RATIO = 0.20
SIHEUNG_RATIO = 0.40


def _round100(value: float) -> int:
    return max(100, int(round(value / 100.0)) * 100)


def pick_normal_price(category: str, rng: random.Random) -> int:
    avg = CATEGORY_AVG_PRICE.get(category, DEFAULT_AVG)
    return _round100(avg * rng.uniform(1 - PRICE_JITTER, 1 + PRICE_JITTER))


def pick_discount(rng: random.Random) -> float:
    return rng.uniform(DISCOUNT_MIN, DISCOUNT_MAX)


def compute_sale_price(normal_price: int, discount: float) -> int:
    # 100원 단위 반올림 오차로 유효 할인율이 30~50%를 벗어나지 않도록 판매가를 클램프.
    hi = math.floor(normal_price * (1 - DISCOUNT_MIN) / 100) * 100  # 할인 30% → 판매가 상한
    lo = math.ceil(normal_price * (1 - DISCOUNT_MAX) / 100) * 100  # 할인 50% → 판매가 하한
    sale = min(max(_round100(normal_price * (1 - discount)), lo), hi)
    return max(100, sale)


def pick_deadline(now: datetime, rng: random.Random) -> datetime:
    return now + timedelta(minutes=rng.choice(DEADLINE_CHOICES))


def pick_store_sale_count(rng: random.Random) -> int:
    return rng.randint(PER_STORE_MIN, PER_STORE_MAX)


def pick_stock(rng: random.Random) -> int:
    return rng.randint(STOCK_MIN, STOCK_MAX)


def build_price(category: str, rng: random.Random) -> tuple[int, int]:
    """정상가·판매가를 생성. 마감시각은 매장당 하나라 여기 포함하지 않는다."""
    normal = pick_normal_price(category, rng)
    return normal, compute_sale_price(normal, pick_discount(rng))


def _pick_titles(category: str, count: int, rng: random.Random) -> list[str]:
    pool = CATEGORY_ITEMS.get(category, DEFAULT_ITEMS)
    if count <= len(pool):
        return rng.sample(pool, count)
    titles = list(pool)
    while len(titles) < count:  # 풀보다 많이 필요하면 중복 허용해 채운다.
        titles.append(rng.choice(pool))
    return titles


def _roundrobin_by_market(stores: list[Store], k: int, rng: random.Random) -> list[Store]:
    """시장별로 묶어 라운드로빈으로 k개 선택 → 특정 시장 쏠림 방지."""
    if k <= 0:
        return []
    groups: dict[int, list[Store]] = defaultdict(list)
    for s in stores:
        groups[s.market_id].append(s)
    queues = list(groups.values())
    for q in queues:
        rng.shuffle(q)
    rng.shuffle(queues)
    dqs = [deque(q) for q in queues]
    picked: list[Store] = []
    while len(picked) < k and any(dqs):
        for dq in dqs:
            if dq:
                picked.append(dq.popleft())
                if len(picked) >= k:
                    break
        dqs = [dq for dq in dqs if dq]
    return picked


async def _units_by_category(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(Category.code, Category.default_unit_code))).all()
    return {code: unit for code, unit in rows}


async def _stores_by_bucket(session: AsyncSession) -> tuple[list[Store], list[Store]]:
    """(시흥, 그 외=서울) 두 버킷으로 분류. 시장 주소 기준(매장 주소는 '시흥대로' 등 오염)."""
    rows = (
        await session.execute(select(Store, Market.address).join(Market, Store.market_id == Market.id))
    ).all()
    siheung: list[Store] = []
    other: list[Store] = []
    for store, address in rows:
        (siheung if address and "시흥" in address else other).append(store)
    return siheung, other


async def select_stores(
    session: AsyncSession,
    rng: random.Random,
    seoul_ratio: float = SEOUL_RATIO,
    siheung_ratio: float = SIHEUNG_RATIO,
) -> list[Store]:
    """지역별 비율로 매장을 뽑는다: 서울 seoul_ratio, 시흥 siheung_ratio."""
    siheung, other = await _stores_by_bucket(session)
    picked_s = _roundrobin_by_market(siheung, round(len(siheung) * siheung_ratio), rng)
    picked_o = _roundrobin_by_market(other, round(len(other) * seoul_ratio), rng)
    return picked_s + picked_o


async def generate_sales(
    session: AsyncSession,
    rng: random.Random,
    now: datetime | None = None,
    seoul_ratio: float = SEOUL_RATIO,
    siheung_ratio: float = SIHEUNG_RATIO,
) -> int:
    now = now or datetime.now(timezone.utc)
    units = await _units_by_category(session)
    stores = await select_stores(session, rng, seoul_ratio, siheung_ratio)
    created = 0
    for st in stores:
        deadline = pick_deadline(now, rng)  # 한 매장의 상품은 마감시각을 공유
        for title in _pick_titles(st.category_code, pick_store_sale_count(rng), rng):
            normal, sale = build_price(st.category_code, rng)
            stock = pick_stock(rng)
            session.add(
                Sale(
                    store_id=st.id,
                    category_code=st.category_code,
                    title=title,
                    image_url=image_url_for(title),
                    normal_price=normal,
                    sale_price=sale,
                    unit_code=units.get(st.category_code, "piece"),
                    min_order=1,
                    total_quantity=stock,
                    remaining_quantity=stock,
                    deadline_at=deadline,
                    status=SaleStatus.ACTIVE,
                )
            )
            created += 1
    await session.commit()
    return created


async def refresh_expired(
    session: AsyncSession, rng: random.Random, now: datetime | None = None
) -> int:
    """마감이 지난 세일의 정상가·할인율·마감시각·이미지를 재생성하고 재고·상태를 되살린다."""
    now = now or datetime.now(timezone.utc)
    expired = (
        (
            await session.execute(
                select(Sale).where(Sale.is_deleted.is_(False), Sale.deadline_at <= now)
            )
        )
        .scalars()
        .all()
    )
    by_store: dict[int, list[Sale]] = defaultdict(list)
    for sale in expired:
        by_store[sale.store_id].append(sale)
    for sales in by_store.values():
        deadline = pick_deadline(now, rng)  # 한 매장의 상품은 마감시각을 공유
        for sale in sales:
            normal, sale_price = build_price(sale.category_code, rng)
            sale.normal_price = normal
            sale.sale_price = sale_price
            sale.image_url = image_url_for(sale.title)
            sale.deadline_at = deadline
            sale.remaining_quantity = sale.total_quantity
            sale.status = SaleStatus.ACTIVE
    await session.commit()
    return len(expired)


async def run_cycle(
    session: AsyncSession, rng: random.Random | None = None, now: datetime | None = None
) -> dict[str, int]:
    """세일이 없으면 초기 생성, 있으면 마감 지난 것 재생성. 워커가 주기적으로 호출."""
    rng = rng or random.Random()
    now = now or datetime.now(timezone.utc)
    total = (
        await session.execute(
            select(func.count()).select_from(Sale).where(Sale.is_deleted.is_(False))
        )
    ).scalar()
    if not total:
        return {"created": await generate_sales(session, rng, now), "refreshed": 0}
    return {"created": 0, "refreshed": await refresh_expired(session, rng, now)}


async def purge_sales(session: AsyncSession) -> None:
    """세일과 이를 참조하는 주문·알림을 모두 비운다(완전 초기화, 되돌릴 수 없음)."""
    await session.execute(
        text("TRUNCATE TABLE sales, orders, notifications RESTART IDENTITY CASCADE")
    )
    await session.commit()
