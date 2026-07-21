from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.models.market import Market
from app.models.store import Store
from app.schemas.market import MarketDetailResponse, MarketResponse
from app.schemas.store import StoreResponse

router = APIRouter(prefix="/markets", tags=["전통시장"])


@router.get("", response_model=list[MarketResponse], summary="반경 내 전통시장 검색")
async def search_markets(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: int = Query(2000, ge=1),
    session: AsyncSession = Depends(get_session),
) -> list[MarketResponse]:
    distance = func.ST_DistanceSphere(
        func.ST_MakePoint(Market.lng, Market.lat),
        func.ST_MakePoint(lng, lat),
    )
    stmt = (
        select(Market, distance)
        .where(Market.is_deleted.is_(False), distance <= radius)
        .order_by(distance)
    )
    out: list[MarketResponse] = []
    for market, dist in (await session.execute(stmt)).all():
        resp = MarketResponse.model_validate(market)
        resp.distance_m = round(dist)
        out.append(resp)
    return out


@router.get("/{market_id}", response_model=MarketDetailResponse, summary="전통시장 상세")
async def get_market(
    market_id: int, session: AsyncSession = Depends(get_session)
) -> MarketDetailResponse:
    market = await session.get(Market, market_id)
    if market is None or market.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.MARKET_NOT_FOUND)
    store_count = (
        await session.execute(
            select(func.count())
            .select_from(Store)
            .where(Store.market_id == market_id, Store.is_deleted.is_(False))
        )
    ).scalar()
    return MarketDetailResponse(**MarketResponse.model_validate(market).model_dump(), store_count=store_count)


@router.get("/{market_id}/stores", response_model=list[StoreResponse], summary="시장 내 매장 목록")
async def list_market_stores(
    market_id: int, session: AsyncSession = Depends(get_session)
) -> list[Store]:
    if await session.get(Market, market_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.MARKET_NOT_FOUND)
    stmt = (
        select(Store)
        .where(Store.market_id == market_id, Store.is_deleted.is_(False))
        .order_by(Store.id)
    )
    return list((await session.execute(stmt)).scalars().all())
