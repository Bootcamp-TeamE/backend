import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.events import bus
from app.config import settings
from app.routers import (
    auth,
    category,
    favorite,
    market,
    notification,
    order,
    owner,
    sale,
    search,
    store,
    subscription,
    unit,
    upload,
)

tags_metadata = [
    {"name": "인증", "description": "구글 로그인·내 정보·개발용 로그인"},
    {"name": "업종", "description": "업종(카테고리) 조회"},
    {"name": "단위", "description": "판매 단위 조회"},
    {"name": "전통시장", "description": "전통시장 검색·상세·소속 매장"},
    {"name": "매장", "description": "매장 조회·등록"},
    {"name": "마감세일", "description": "마감세일 등록·조회·조기마감"},
    {"name": "검색", "description": "반경 내 마감세일 검색"},
    {"name": "주문", "description": "주문·예약 생성·결제·취소·수령"},
    {"name": "알림", "description": "결제 완료 등 알림 조회·읽음 처리"},
    {"name": "구독", "description": "관심 조건 알림 구독 생성·조회·수정"},
    {"name": "점주", "description": "점주 대시보드 요약 지표·SSE 실시간"},
    {"name": "시스템", "description": "헬스체크"},
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 워커(별도 프로세스)가 발행하는 SSE 깨우기 신호를 받는 리스너.
    listener = asyncio.create_task(bus.listen())
    yield
    listener.cancel()


app = FastAPI(
    title="마감할인 API",
    version="0.1.0",
    description="전통시장 마감할인 서비스 API",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(unit.router, prefix="/api/v1")
app.include_router(category.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(store.router, prefix="/api/v1")
app.include_router(favorite.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")

# 업로드 이미지 정적 서빙. check_dir=False → 디렉토리가 없어도 기동 실패 안 함(첫 업로드 시 생성).
app.mount("/uploads", StaticFiles(directory=settings.upload_dir, check_dir=False), name="uploads")
app.include_router(sale.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(order.router, prefix="/api/v1")
app.include_router(notification.router, prefix="/api/v1")
app.include_router(subscription.router, prefix="/api/v1")
app.include_router(owner.router, prefix="/api/v1")


@app.get("/health", tags=["시스템"], summary="헬스체크")
async def health() -> dict[str, str]:
    return {"status": "ok"}
