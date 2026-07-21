from pydantic import BaseModel, ConfigDict


class MarketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    market_type: str | None
    address: str | None
    lat: float
    lng: float
    distance_m: float | None = None


class MarketDetailResponse(MarketResponse):
    store_count: int
