from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.deps import get_current_user
from app.database import get_session
from app.models.favorite import Favorite
from app.models.store import Store
from app.models.user import User
from app.schemas.store import StoreResponse

router = APIRouter(tags=["관심매장"])


@router.post(
    "/stores/{store_id}/favorite",
    status_code=status.HTTP_201_CREATED,
    summary="관심 매장 등록",
)
async def add_favorite(
    store_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    store = await session.get(Store, store_id)
    if store is None or store.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    # UNIQUE(user_id, store_id) 위에서 멱등 — 이미 있으면 아무 일 없음.
    stmt = (
        pg_insert(Favorite)
        .values(user_id=current_user.id, store_id=store_id)
        .on_conflict_do_nothing(index_elements=["user_id", "store_id"])
    )
    await session.execute(stmt)
    await session.commit()
    return {"favorited": True}


@router.delete(
    "/stores/{store_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="관심 매장 해제",
)
async def remove_favorite(
    store_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # 없어도 에러 없이 204(멱등).
    await session.execute(
        delete(Favorite).where(
            Favorite.user_id == current_user.id, Favorite.store_id == store_id
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/favorites", response_model=list[StoreResponse], summary="관심 매장 목록")
async def list_favorites(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Store]:
    stmt = (
        select(Store)
        .join(Favorite, Favorite.store_id == Store.id)
        .where(Favorite.user_id == current_user.id, Store.is_deleted.is_(False))
        .order_by(Favorite.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
