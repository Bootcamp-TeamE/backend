from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.database import get_session
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse

router = APIRouter(tags=["알림"])


@router.get("/notifications", response_model=list[NotificationResponse], summary="내 알림 목록")
async def list_notifications(
    user_id: int, session: AsyncSession = Depends(get_session)
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id, Notification.is_deleted.is_(False))
        .order_by(Notification.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    summary="알림 읽음 처리",
)
async def read_notification(
    notification_id: int, session: AsyncSession = Depends(get_session)
) -> Notification:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.NOTIFICATION_NOT_FOUND)
    notification.is_read = True
    await session.commit()
    await session.refresh(notification)
    return notification
