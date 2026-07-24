from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.order import OrderStatus


class OrderCreate(BaseModel):
    user_id: int
    sale_id: int
    quantity: int = 1

    @model_validator(mode="after")
    def _check(self) -> "OrderCreate":
        if self.quantity <= 0:
            raise ValueError("수량은 양수여야 합니다")
        return self


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    sale_id: int
    quantity: int
    total_price: int
    status: OrderStatus
    qr_token: str | None
    pickup_no: str | None
    reserved_at: datetime
    expires_at: datetime
    paid_at: datetime | None
    picked_up_at: datetime | None
    refunded_at: datetime | None
