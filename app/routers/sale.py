import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.events.publisher import EventPublisher, get_publisher
from app.models.category import Category
from app.models.sale import Sale, SaleStatus
from app.models.store import Store
from app.models.unit import Unit
from app.schemas.sale import SaleCreate, SaleResponse, SaleUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["마감세일"])


@router.post(
    "/stores/{store_id}/sales",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="마감세일 등록",
)
async def create_sale(
    store_id: int,
    payload: SaleCreate,
    session: AsyncSession = Depends(get_session),
    publisher: EventPublisher = Depends(get_publisher),
) -> Sale:
    store = await session.get(Store, store_id)
    if store is None or store.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    category_code = payload.category_code or store.category_code
    category = await session.get(Category, category_code)
    if category is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.UNKNOWN_CATEGORY)
    unit_code = payload.unit_code or category.default_unit_code
    if await session.get(Unit, unit_code) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.UNKNOWN_UNIT)
    sale = Sale(
        store_id=store.id,
        category_code=category_code,
        title=payload.title,
        description=payload.description,
        image_url=payload.image_url,
        normal_price=payload.normal_price,
        sale_price=payload.sale_price,
        unit_code=unit_code,
        min_order=payload.min_order,
        total_quantity=payload.total_quantity,
        remaining_quantity=payload.total_quantity,
        deadline_at=payload.deadline_at,
        status=SaleStatus.ACTIVE,
    )
    session.add(sale)
    await session.commit()
    await session.refresh(sale)

    # 발견 fanout 알림 트리거. best-effort — 발행 실패해도 세일 등록은 이미 커밋됨.
    try:
        await publisher.publish("sale.created", {"sale_id": sale.id})
    except Exception:
        logger.exception("sale.created 이벤트 발행 실패 sale_id=%s", sale.id)

    return sale


@router.get("/sales/{sale_id}", response_model=SaleResponse, summary="마감세일 상세")
async def get_sale(sale_id: int, session: AsyncSession = Depends(get_session)) -> Sale:
    sale = await session.get(Sale, sale_id)
    if sale is None or sale.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.SALE_NOT_FOUND)
    return sale


@router.get("/sales", response_model=list[SaleResponse], summary="활성 마감세일 목록")
async def list_sales(
    category: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[Sale]:
    stmt = select(Sale).where(
        Sale.status == SaleStatus.ACTIVE,
        Sale.is_deleted.is_(False),
        Sale.deadline_at > datetime.now(timezone.utc),
    )
    if category is not None:
        stmt = stmt.where(Sale.category_code == category)
    stmt = stmt.order_by(Sale.deadline_at)
    return list((await session.execute(stmt)).scalars().all())


@router.patch("/sales/{sale_id}", response_model=SaleResponse, summary="마감세일 수정(추가 할인·조기 마감)")
async def update_sale(
    sale_id: int, payload: SaleUpdate, session: AsyncSession = Depends(get_session)
) -> Sale:
    sale = await session.get(Sale, sale_id)
    if sale is None or sale.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.SALE_NOT_FOUND)
    if payload.sale_price is not None:
        if payload.sale_price <= 0 or payload.sale_price >= sale.normal_price:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.INVALID_SALE_PRICE)
        sale.sale_price = payload.sale_price
    if payload.status is not None:
        sale.status = payload.status
    await session.commit()
    await session.refresh(sale)
    return sale
