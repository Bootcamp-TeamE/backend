from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.category import Category
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["업종"])


@router.get("", response_model=list[CategoryResponse], summary="업종 목록 조회")
async def list_categories(session: AsyncSession = Depends(get_session)) -> list[Category]:
    stmt = (
        select(Category)
        .where(Category.is_active.is_(True), Category.is_deleted.is_(False))
        .order_by(Category.sort_order)
    )
    return list((await session.execute(stmt)).scalars().all())
