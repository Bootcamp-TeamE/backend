from pydantic import BaseModel, ConfigDict


class StoreCreate(BaseModel):
    category_code: str
    name: str
    lat: float
    lng: float
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
