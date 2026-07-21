from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.models.category import Category
from app.models.market import Market
from app.models.store import Store
from app.schemas.store import StoreCreate, StoreResponse

router = APIRouter(prefix="/stores", tags=["매장"])


@router.get("/{store_id}", response_model=StoreResponse, summary="매장 상세")
async def get_store(store_id: int, session: AsyncSession = Depends(get_session)) -> Store:
    store = await session.get(Store, store_id)
    if store is None or store.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    return store


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED, summary="매장 등록")
async def create_store(
    payload: StoreCreate, session: AsyncSession = Depends(get_session)
) -> Store:
    if await session.get(Category, payload.category_code) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.UNKNOWN_CATEGORY)
    if payload.market_id is not None and await session.get(Market, payload.market_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.MARKET_NOT_FOUND)
    store = Store(
        market_id=payload.market_id,
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
