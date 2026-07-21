from fastapi import FastAPI

from app.routers import category, market, store

tags_metadata = [
    {"name": "업종", "description": "업종(카테고리) 조회"},
    {"name": "전통시장", "description": "전통시장 검색·상세·소속 매장"},
    {"name": "매장", "description": "매장 조회·등록"},
    {"name": "시스템", "description": "헬스체크"},
]

app = FastAPI(
    title="마감할인 API",
    version="0.1.0",
    description="전통시장 마감할인 서비스 API",
    openapi_tags=tags_metadata,
)

app.include_router(category.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(store.router, prefix="/api/v1")


@app.get("/health", tags=["시스템"], summary="헬스체크")
async def health() -> dict[str, str]:
    return {"status": "ok"}
