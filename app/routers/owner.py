import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import errors
from app.core.deps import get_current_owner, get_user_from_query_token
from app.database import get_session, get_sessionmaker
from app.events import bus
from app.models.store import Store
from app.models.user import Role, User
from app.schemas.dashboard import DashboardResponse
from app.schemas.store import StoreResponse
from app.services.dashboard import compute_dashboard

router = APIRouter(prefix="/owner", tags=["점주"])

KEEPALIVE_SECONDS = 15


@router.get("/store", response_model=StoreResponse, summary="내 매장 조회")
async def owner_store(
    owner: User = Depends(get_current_owner), session: AsyncSession = Depends(get_session)
) -> Store:
    store = (
        await session.execute(
            select(Store).where(Store.owner_id == owner.id, Store.is_deleted.is_(False))
        )
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    return store


@router.get("/dashboard", response_model=DashboardResponse, summary="점주 대시보드 요약 지표")
async def owner_dashboard(
    owner: User = Depends(get_current_owner), session: AsyncSession = Depends(get_session)
) -> dict:
    data = await compute_dashboard(session, owner.id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    return data


@router.get("/dashboard/stream", summary="점주 대시보드 SSE 실시간")
async def owner_dashboard_stream(
    owner: User = Depends(get_user_from_query_token),
    maker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> StreamingResponse:
    # SSE는 쿼리 토큰 인증이라 get_current_owner를 못 쓴다 — role 검사를 함수 안에서 직접 한다.
    if owner.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=errors.OWNER_ONLY)
    # 스트림 시작 후엔 404를 낼 수 없으므로 연결 전에 매장 존재를 확인(짧은 세션).
    async with maker() as session:
        if await compute_dashboard(session, owner.id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=errors.STORE_NOT_FOUND)
    return StreamingResponse(_dashboard_events(owner.id, maker), media_type="text/event-stream")


async def _dashboard_events(owner_id: int, maker: async_sessionmaker[AsyncSession]):
    async def snapshot_frame() -> str:
        # 스냅샷마다 짧은 세션을 열고 닫아 연결 내내 DB 커넥션을 붙잡지 않는다.
        async with maker() as session:
            data = await compute_dashboard(session, owner_id)
        return f"data: {json.dumps(data)}\n\n"

    # 스냅샷 계산과 구독 사이에 온 이벤트를 놓치지 않도록 구독을 먼저 건다.
    queue = bus.subscribe(bus.DASHBOARD, owner_id)
    try:
        yield await snapshot_frame()  # 연결 즉시 최신 스냅샷 1건
        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                yield await snapshot_frame()  # 변경 신호 → 재계산 후 push
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # 죽은 연결 감지 + 프록시 idle 방지
    finally:
        bus.unsubscribe(bus.DASHBOARD, owner_id, queue)
