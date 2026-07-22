from pydantic import BaseModel, ConfigDict, model_validator


def _validate_ranges(
    min_discount_rate: int | None,
    max_price: int | None,
    radius_m: int | None,
    receive_from: int | None,
    receive_to: int | None,
) -> None:
    if min_discount_rate is not None and not 0 <= min_discount_rate <= 100:
        raise ValueError("최소 할인율은 0~100 사이여야 합니다")
    if max_price is not None and max_price <= 0:
        raise ValueError("가격 상한은 양수여야 합니다")
    if radius_m is not None and radius_m <= 0:
        raise ValueError("반경은 양수여야 합니다")
    if receive_from is not None and not 0 <= receive_from <= 24:
        raise ValueError("수신 시작 시각은 0~24 사이여야 합니다")
    if receive_to is not None and not 0 <= receive_to <= 24:
        raise ValueError("수신 종료 시각은 0~24 사이여야 합니다")
    if receive_from is not None and receive_to is not None and receive_from >= receive_to:
        raise ValueError("수신 시작 시각은 종료 시각보다 빨라야 합니다")


class SubscriptionCreate(BaseModel):
    user_id: int
    categories: list[str]
    lat: float
    lng: float
    min_discount_rate: int = 0
    max_price: int | None = None
    radius_m: int = 1000
    receive_from: int = 0
    receive_to: int = 24
    push_enabled: bool = True
    opted_out: bool = False

    @model_validator(mode="after")
    def _check(self) -> "SubscriptionCreate":
        if not self.categories:
            raise ValueError("관심 업종을 하나 이상 선택해야 합니다")
        _validate_ranges(
            self.min_discount_rate, self.max_price, self.radius_m,
            self.receive_from, self.receive_to,
        )
        return self


class SubscriptionUpdate(BaseModel):
    categories: list[str] | None = None
    lat: float | None = None
    lng: float | None = None
    min_discount_rate: int | None = None
    max_price: int | None = None
    radius_m: int | None = None
    receive_from: int | None = None
    receive_to: int | None = None
    push_enabled: bool | None = None
    opted_out: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> "SubscriptionUpdate":
        if self.categories is not None and not self.categories:
            raise ValueError("관심 업종을 하나 이상 선택해야 합니다")
        _validate_ranges(
            self.min_discount_rate, self.max_price, self.radius_m,
            self.receive_from, self.receive_to,
        )
        return self


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    categories: list[str]
    lat: float
    lng: float
    min_discount_rate: int
    max_price: int | None
    radius_m: int
    receive_from: int
    receive_to: int
    push_enabled: bool
    opted_out: bool
