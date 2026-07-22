import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import errors
from app.database import get_session, get_sessionmaker
from app.events import bus
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse

router = APIRouter(tags=["알림"])

KEEPALIVE_SECONDS = 15
RECENT_LIMIT = 20


@router.get("/notifications", response_model=list[NotificationResponse], summary="내 알림 목록")
async def list_notifications(
    user_id: int, unread: bool = False, session: AsyncSession = Depends(get_session)
) -> list[Notification]:
    stmt = select(Notification).where(
        Notification.user_id == user_id, Notification.is_deleted.is_(False)
    )
    if unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/notifications/unread-count", summary="안읽은 알림 개수")
async def unread_count(
    user_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    count = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                Notification.is_deleted.is_(False),
            )
        )
    ).scalar()
    return {"count": count}


@router.patch("/notifications/read-all", summary="전체 읽음 처리")
async def read_all(
    user_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    result = await session.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.is_deleted.is_(False),
        )
        .values(is_read=True)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    await bus.publish(bus.USER, user_id)  # 읽음 상태 변경 → SSE 갱신
    return {"updated": result.rowcount}


@router.get("/notifications/stream", summary="내 알림 SSE 실시간")
async def notifications_stream(
    user_id: int,
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> StreamingResponse:
    return StreamingResponse(_notification_events(user_id, maker), media_type="text/event-stream")


async def _recent_notifications(session: AsyncSession, user_id: int) -> list[dict]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id, Notification.is_deleted.is_(False))
        .order_by(Notification.created_at.desc())
        .limit(RECENT_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [NotificationResponse.model_validate(r).model_dump(mode="json") for r in rows]


async def _notification_events(user_id: int, maker: async_sessionmaker[AsyncSession]):
    async def frame() -> str:
        async with maker() as session:  # 스냅샷마다 짧은 세션 (연결 내내 DB 연결 안 잡음)
            data = await _recent_notifications(session, user_id)
        return f"data: {json.dumps(data)}\n\n"

    queue = bus.subscribe(bus.USER, user_id)
    try:
        yield await frame()  # 연결 즉시 최근 알림
        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                yield await frame()  # 새 알림 신호 → 재조회 후 push
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        bus.unsubscribe(bus.USER, user_id, queue)


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
    await bus.publish(bus.USER, notification.user_id)  # 읽음 상태 변경 → SSE 갱신
    return notification
