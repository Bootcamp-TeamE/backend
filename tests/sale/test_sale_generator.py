"""sale_generator: 가격·할인·마감·품목명 규칙과 생성/재생성 DB 동작 검증."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from app.models.category import Category
from app.models.market import Market
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.services import sale_generator as gen

CATEGORIES = [
    ("butcher", "정육", 1, "geun"),
    ("seafood", "수산", 2, "kg"),
    ("greengrocer", "청과", 3, "kg"),
    ("sidedish", "반찬", 4, "pack"),
    ("ricecake", "떡", 5, "pack"),
    ("tofu_namul", "두부·나물", 6, "piece"),
    ("egg_dairy", "계란·유제품", 7, "pan"),
    ("streetfood", "시장먹거리", 8, "piece"),
    ("flower", "화훼", 9, "songi"),
]


# ── 순수 로직 ──────────────────────────────────────────────


def test_discount_within_30_to_50_percent():
    rng = random.Random(1)
    for _ in range(2000):
        d = gen.pick_discount(rng)
        assert 0.30 <= d <= 0.50


def test_normal_price_within_20pct_of_avg_and_100_won_unit():
    rng = random.Random(2)
    for code, avg in gen.CATEGORY_AVG_PRICE.items():
        for _ in range(500):
            p = gen.pick_normal_price(code, rng)
            assert p % 100 == 0
            assert avg * 0.8 - 50 <= p <= avg * 1.2 + 50


def test_sale_price_below_normal_and_keeps_30_to_50_discount():
    for normal in range(2000, 50001, 300):
        for discount in (0.30, 0.33, 0.37, 0.44, 0.50):
            sp = gen.compute_sale_price(normal, discount)
            assert sp % 100 == 0
            assert 100 <= sp < normal
            effective = 1 - sp / normal  # 100원 반올림 후에도 30~50% 유지
            assert 0.30 - 1e-9 <= effective <= 0.50 + 1e-9


def test_deadline_is_1_to_3h_in_10min_steps():
    rng = random.Random(3)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    for _ in range(2000):
        d = gen.pick_deadline(now, rng)
        minutes = round((d - now).total_seconds() / 60)
        assert minutes in gen.DEADLINE_CHOICES
        assert 60 <= minutes <= 180 and minutes % 10 == 0


def test_store_sale_count_is_2_to_5():
    rng = random.Random(4)
    seen = set()
    for _ in range(2000):
        c = gen.pick_store_sale_count(rng)
        assert 2 <= c <= 5
        seen.add(c)
    assert seen == {2, 3, 4, 5}


def test_titles_are_distinct_real_products_without_모둠():
    rng = random.Random(5)
    for code, pool in gen.CATEGORY_ITEMS.items():
        for count in (2, 3, 4, 5):
            titles = gen._pick_titles(code, count, rng)
            assert len(titles) == count
            assert len(set(titles)) == count  # 중복 없음
            assert set(titles) <= set(pool)
            assert all("모둠" not in t for t in titles)


def test_every_catalog_item_has_an_image():
    for pool in gen.CATEGORY_ITEMS.values():
        for title in pool:
            assert title in gen.PRODUCT_IMAGES  # 모든 상품에 이미지 존재


def test_image_url_is_local_uploads_path_per_title():
    a = gen.image_url_for("삼겹살")
    assert a == "/uploads/products/samgyeopsal.jpg"
    assert gen.image_url_for("고등어") != a  # 다른 상품 → 다른 경로
    assert gen.image_url_for("존재하지않는상품") is None  # 매핑 없으면 None


# ── DB 생성/재생성 ─────────────────────────────────────────


async def _seed_catalog(session, *, siheung_stores: int, seoul_stores: int):
    for code, name_ko, order, unit in CATEGORIES:
        session.add(Category(code=code, name_ko=name_ko, sort_order=order, default_unit_code=unit))
    sih = Market(name="시흥삼미시장", market_type="전통시장", address="경기도 시흥시 삼미로", lat=37.44, lng=126.78)
    seo = Market(name="서울중앙시장", market_type="전통시장", address="서울특별시 중구 청계천로", lat=37.56, lng=126.99)
    session.add_all([sih, seo])
    await session.flush()
    for i in range(siheung_stores):
        session.add(Store(name=f"시흥가게{i}", category_code="butcher", market_id=sih.id,
                           owner_id=None, address="경기도 시흥시", lat=37.44, lng=126.78))
    for i in range(seoul_stores):
        session.add(Store(name=f"서울가게{i}", category_code="seafood", market_id=seo.id,
                          owner_id=None, address="서울특별시 중구", lat=37.56, lng=126.99))
    await session.commit()


@pytest.mark.asyncio
async def test_select_stores_applies_region_ratios(session):
    await _seed_catalog(session, siheung_stores=10, seoul_stores=100)
    rng = random.Random(7)
    picked = await gen.select_stores(session, rng, seoul_ratio=0.20, siheung_ratio=0.40)
    cats = [s.category_code for s in picked]
    assert cats.count("butcher") == round(10 * 0.40)  # 시흥 = 정육 매장
    assert cats.count("seafood") == round(100 * 0.20)  # 서울 = 수산 매장


@pytest.mark.asyncio
async def test_generate_sales_makes_2_to_5_active_sales_per_store(session):
    await _seed_catalog(session, siheung_stores=5, seoul_stores=5)
    rng = random.Random(8)
    created = await gen.generate_sales(session, rng, seoul_ratio=1.0, siheung_ratio=1.0)

    sales = (await session.execute(Sale.__table__.select())).all()
    assert created == len(sales)
    by_store: dict[int, int] = {}
    for row in sales:
        by_store[row.store_id] = by_store.get(row.store_id, 0) + 1
        assert row.status == SaleStatus.ACTIVE
        assert 100 <= row.sale_price < row.normal_price
        assert row.remaining_quantity == row.total_quantity
        assert row.image_url and row.image_url.startswith("/uploads/products/")
    assert len(by_store) == 10  # 모든 매장에 생성
    assert all(2 <= n <= 5 for n in by_store.values())


@pytest.mark.asyncio
async def test_generate_sales_shares_one_deadline_per_store(session):
    await _seed_catalog(session, siheung_stores=5, seoul_stores=5)
    await gen.generate_sales(session, random.Random(12), seoul_ratio=1.0, siheung_ratio=1.0)

    sales = (await session.execute(Sale.__table__.select())).all()
    deadlines_by_store: dict[int, set] = {}
    for row in sales:
        deadlines_by_store.setdefault(row.store_id, set()).add(row.deadline_at)
    assert all(len(dls) == 1 for dls in deadlines_by_store.values())


@pytest.mark.asyncio
async def test_refresh_expired_shares_one_deadline_per_store(session):
    await _seed_catalog(session, siheung_stores=1, seoul_stores=0)
    store_id = (await session.execute(Store.__table__.select())).first().id
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    session.add_all([
        Sale(store_id=store_id, category_code="butcher", title=t, normal_price=10000,
             sale_price=6000, unit_code="geun", min_order=1, total_quantity=10,
             remaining_quantity=0, deadline_at=past, status=SaleStatus.CLOSED)
        for t in ("삼겹살", "목살", "등심")
    ])
    await session.commit()

    await gen.refresh_expired(session, random.Random(13), now)
    rows = (await session.execute(Sale.__table__.select())).all()
    assert len({r.deadline_at for r in rows}) == 1  # 세 상품 모두 같은 마감시각
    assert all(r.deadline_at > now for r in rows)


@pytest.mark.asyncio
async def test_refresh_expired_only_revives_past_deadline(session):
    await _seed_catalog(session, siheung_stores=1, seoul_stores=0)
    store_id = (await session.execute(Store.__table__.select())).first().id
    now = datetime.now(timezone.utc)
    expired = Sale(store_id=store_id, category_code="butcher", title="삼겹살", normal_price=10000,
                   sale_price=6000, unit_code="geun", min_order=1, total_quantity=10,
                   remaining_quantity=0, deadline_at=now - timedelta(hours=1), status=SaleStatus.CLOSED)
    fresh = Sale(store_id=store_id, category_code="butcher", title="목살", normal_price=12000,
                 sale_price=7000, unit_code="geun", min_order=1, total_quantity=8,
                 remaining_quantity=3, deadline_at=now + timedelta(hours=2), status=SaleStatus.ACTIVE)
    session.add_all([expired, fresh])
    await session.commit()

    count = await gen.refresh_expired(session, random.Random(9), now)
    assert count == 1
    await session.refresh(expired)
    await session.refresh(fresh)
    # 만료건: 되살아남
    assert expired.status == SaleStatus.ACTIVE
    assert expired.deadline_at > now
    assert expired.remaining_quantity == expired.total_quantity
    # 미래건: 그대로
    assert fresh.remaining_quantity == 3
    assert fresh.deadline_at > now


@pytest.mark.asyncio
async def test_run_cycle_creates_when_empty_then_refreshes(session):
    await _seed_catalog(session, siheung_stores=3, seoul_stores=3)
    rng = random.Random(10)
    first = await gen.run_cycle(session, rng)
    assert first["created"] > 0 and first["refreshed"] == 0

    # 두 번째 호출: 이미 있으므로 생성 0, 마감 지난 게 없으면 refresh 0
    second = await gen.run_cycle(session, rng)
    assert second["created"] == 0


@pytest.mark.asyncio
async def test_purge_sales_empties_table(session):
    await _seed_catalog(session, siheung_stores=2, seoul_stores=0)
    await gen.generate_sales(session, random.Random(11), seoul_ratio=1.0, siheung_ratio=1.0)
    assert (await session.execute(Sale.__table__.select())).all()

    await gen.purge_sales(session)
    assert not (await session.execute(Sale.__table__.select())).all()
