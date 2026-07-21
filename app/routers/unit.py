from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.unit import Unit
from app.schemas.unit import UnitResponse

router = APIRouter(prefix="/units", tags=["단위"])


@router.get("", response_model=list[UnitResponse], summary="판매 단위 목록")
async def list_units(session: AsyncSession = Depends(get_session)) -> list[Unit]:
    stmt = (
        select(Unit)
        .where(Unit.is_active.is_(True), Unit.is_deleted.is_(False))
        .order_by(Unit.sort_order)
    )
    return list((await session.execute(stmt)).scalars().all())
