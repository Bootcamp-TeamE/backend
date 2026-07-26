from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.models.sale import SaleStatus


class SaleCreate(BaseModel):
    title: str
    normal_price: int
    sale_price: int
    total_quantity: int
    deadline_at: datetime
    description: str | None = None
    image_url: str | None = None  # 미지정 시 프론트가 카테고리 톤 썸네일로 폴백
    category_code: str | None = None  # 미지정 시 매장 카테고리 상속
    unit_code: str | None = None  # 미지정 시 매장 카테고리 기본 단위 상속
    min_order: int = 1

    @model_validator(mode="after")
    def _check(self) -> "SaleCreate":
        if self.normal_price <= 0 or self.sale_price <= 0:
            raise ValueError("가격은 양수여야 합니다")
        if self.sale_price >= self.normal_price:
            raise ValueError("할인가는 정상가보다 낮아야 합니다")
        if self.total_quantity <= 0 or self.min_order <= 0:
            raise ValueError("수량은 양수여야 합니다")
        return self


class SaleUpdate(BaseModel):
    status: SaleStatus | None = None
    sale_price: int | None = None


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    category_code: str
    title: str
    description: str | None
    image_url: str | None
    normal_price: int
    sale_price: int
    unit_code: str
    min_order: int
    total_quantity: int
    remaining_quantity: int
    deadline_at: datetime
    status: SaleStatus

    @computed_field
    @property
    def discount_rate(self) -> int:
        return round((self.normal_price - self.sale_price) / self.normal_price * 100)


class SaleSearchResponse(SaleResponse):
    """반경 검색 결과 — 매장명·거리·좌표를 조인해 함께 내려준다(홈 리스트·지도용)."""

    store_name: str
    store_distance_m: float | None = None
    lat: float
    lng: float
