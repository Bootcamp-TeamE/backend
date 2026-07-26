from pydantic import BaseModel, ConfigDict


class StoreCreate(BaseModel):
    category_code: str
    name: str
    lat: float
    lng: float
    market_id: int | None = None
    address: str | None = None


class StoreUpdate(BaseModel):
    category_code: str | None = None
    name: str | None = None
    lat: float | None = None
    lng: float | None = None
    market_id: int | None = None
    address: str | None = None


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int | None
    owner_id: int | None
    category_code: str
    name: str
    address: str | None
    lat: float
    lng: float


class StoreDetailResponse(StoreResponse):
    """매장 상세 — 관심 매장 등록 수 포함."""

    favorite_count: int = 0
