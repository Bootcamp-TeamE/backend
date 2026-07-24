import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class OrderStatus(str, enum.Enum):
    RESERVED = "reserved"
    PAID = "paid"
    PICKED_UP = "picked_up"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"  # 결제 후 픽업 데드라인 경과 → 자동 환불(no-show)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), default=OrderStatus.RESERVED, index=True, nullable=False
    )
    qr_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pickup_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
