from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.models.category import Category
from app.models.favorite import Favorite
from app.models.market import Market
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.schemas.sale import SaleResponse
from app.schemas.store import StoreCreate, StoreDetailResponse, StoreResponse, StoreUpdate

router = APIRouter(prefix="/stores", tags=["매장"])


@router.get("/{store_id}", response_model=StoreDetailResponse, summary="매장 상세")
async def get_store(
    store_id: int, session: AsyncSession = Depends(get_session)
) -> StoreDetailResponse:
    store = await session.get(Store, store_id)
    if store is None or store.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    favorite_count = (
        await session.execute(
            select(func.count()).select_from(Favorite).where(Favorite.store_id == store_id)
        )
    ).scalar()
    return StoreDetailResponse(
        **StoreResponse.model_validate(store).model_dump(), favorite_count=favorite_count
    )


@router.get("/{store_id}/sales", response_model=list[SaleResponse], summary="매장 세일 목록")
async def list_store_sales(
    store_id: int, session: AsyncSession = Depends(get_session)
) -> list[Sale]:
    store = await session.get(Store, store_id)
    if store is None or store.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    stmt = (
        select(Sale)
        .where(Sale.store_id == store_id, Sale.is_deleted.is_(False))
        .order_by(Sale.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED, summary="매장 등록")
async def create_store(
    payload: StoreCreate, session: AsyncSession = Depends(get_session)
) -> Store:
    if await session.get(Category, payload.category_code) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.UNKNOWN_CATEGORY)
    if payload.market_id is not None and await session.get(Market, payload.market_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.MARKET_NOT_FOUND)
    # 1계정=1매장 — 이미 매장을 가진 점주면 거절(UNIQUE owner_id 위반 방지).
    if payload.owner_id is not None:
        if await session.get(User, payload.owner_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.USER_NOT_FOUND)
        existing = (
            await session.execute(
                select(Store).where(
                    Store.owner_id == payload.owner_id, Store.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=errors.STORE_ALREADY_OWNED)
    store = Store(
        market_id=payload.market_id,
        owner_id=payload.owner_id,
        category_code=payload.category_code,
        name=payload.name,
        address=payload.address,
        lat=payload.lat,
        lng=payload.lng,
    )
    session.add(store)
    await session.commit()
    await session.refresh(store)
    return store


@router.patch("/{store_id}", response_model=StoreResponse, summary="매장 수정")
async def update_store(
    store_id: int, payload: StoreUpdate, session: AsyncSession = Depends(get_session)
) -> Store:
    store = await session.get(Store, store_id)
    if store is None or store.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    data = payload.model_dump(exclude_unset=True)
    if "category_code" in data and await session.get(Category, data["category_code"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.UNKNOWN_CATEGORY)
    if (
        data.get("market_id") is not None
        and await session.get(Market, data["market_id"]) is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.MARKET_NOT_FOUND)
    for field, value in data.items():
        setattr(store, field, value)
    await session.commit()
    await session.refresh(store)
    return store
