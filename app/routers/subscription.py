from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.models.category import Category
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)

router = APIRouter(tags=["구독"])


async def _ensure_categories_exist(session: AsyncSession, codes: list[str]) -> None:
    found = set(
        (await session.execute(select(Category.code).where(Category.code.in_(codes)))).scalars()
    )
    if set(codes) - found:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors.UNKNOWN_CATEGORY)


@router.post(
    "/subscriptions",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="구독 조건 생성",
)
async def create_subscription(
    payload: SubscriptionCreate, session: AsyncSession = Depends(get_session)
) -> Subscription:
    if await session.get(User, payload.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.USER_NOT_FOUND)
    await _ensure_categories_exist(session, payload.categories)

    subscription = Subscription(**payload.model_dump())
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)
    return subscription


@router.get("/subscriptions", response_model=list[SubscriptionResponse], summary="내 구독 목록")
async def list_subscriptions(
    user_id: int, session: AsyncSession = Depends(get_session)
) -> list[Subscription]:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_deleted.is_(False))
        .order_by(Subscription.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="구독 조건 수정(수신여부·수신거부 포함)",
)
async def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdate,
    session: AsyncSession = Depends(get_session),
) -> Subscription:
    subscription = await session.get(Subscription, subscription_id)
    if subscription is None or subscription.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.SUBSCRIPTION_NOT_FOUND)

    changes = payload.model_dump(exclude_unset=True)
    if "categories" in changes:
        await _ensure_categories_exist(session, changes["categories"])
    for field, value in changes.items():
        setattr(subscription, field, value)

    await session.commit()
    await session.refresh(subscription)
    return subscription


@router.delete(
    "/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="구독 삭제(soft delete)",
)
async def delete_subscription(
    subscription_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    subscription = await session.get(Subscription, subscription_id)
    if subscription is None or subscription.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.SUBSCRIPTION_NOT_FOUND)
    subscription.is_deleted = True
    await session.commit()
