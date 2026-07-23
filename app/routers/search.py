from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.subscription import Subscription
from app.schemas.sale import SaleResponse, SaleSearchResponse

router = APIRouter(prefix="/search", tags=["검색"])


@router.get("/sales", response_model=list[SaleSearchResponse], summary="반경 내 마감세일 검색")
async def search_sales(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: int = Query(2000, ge=1),
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SaleSearchResponse]:
    distance = func.ST_DistanceSphere(
        func.ST_MakePoint(Store.lng, Store.lat),
        func.ST_MakePoint(lng, lat),
    )
    stmt = (
        select(Sale, Store.name, Store.lat, Store.lng, distance.label("distance_m"))
        .join(Store, Sale.store_id == Store.id)
        .where(
            Sale.status == SaleStatus.ACTIVE,
            Sale.is_deleted.is_(False),
            Sale.deadline_at > datetime.now(timezone.utc),
            distance <= radius,
        )
        .order_by(distance)
    )
    if category is not None:
        stmt = stmt.where(Sale.category_code == category)

    results: list[SaleSearchResponse] = []
    for sale, store_name, store_lat, store_lng, dist in (await session.execute(stmt)).all():
        base = SaleResponse.model_validate(sale).model_dump()
        base.pop("discount_rate", None)  # computed_field — 재계산됨
        results.append(
            SaleSearchResponse(
                **base,
                store_name=store_name,
                store_distance_m=dist,
                lat=store_lat,
                lng=store_lng,
            )
        )
    return results


@router.get("/reach", summary="예상 알림 도달 수(점주 등록 보조)")
async def search_reach(
    lat: float = Query(...),
    lng: float = Query(...),
    category: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """이 위치·업종의 세일이 올라오면 알림받을 구독 유저 수. 반경은 각 구독의 radius_m 기준."""
    distance = func.ST_DistanceSphere(
        func.ST_MakePoint(Subscription.lng, Subscription.lat),
        func.ST_MakePoint(lng, lat),
    )
    stmt = select(func.count()).select_from(Subscription).where(
        Subscription.is_deleted.is_(False),
        Subscription.opted_out.is_(False),
        Subscription.push_enabled.is_(True),
        Subscription.categories.any(category),
        distance <= Subscription.radius_m,
    )
    return {"reach": (await session.execute(stmt)).scalar()}
