from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.schemas.sale import SaleResponse

router = APIRouter(prefix="/search", tags=["검색"])


@router.get("/sales", response_model=list[SaleResponse], summary="반경 내 마감세일 검색")
async def search_sales(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: int = Query(2000, ge=1),
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[Sale]:
    distance = func.ST_DistanceSphere(
        func.ST_MakePoint(Store.lng, Store.lat),
        func.ST_MakePoint(lng, lat),
    )
    stmt = (
        select(Sale)
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
    return list((await session.execute(stmt)).scalars().all())
