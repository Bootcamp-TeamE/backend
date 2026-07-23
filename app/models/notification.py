import enum

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class NotificationType(str, enum.Enum):
    ORDER_PAID = "order_paid"            # 트랜잭션: 결제 완료
    ORDER_PICKED_UP = "order_picked_up"  # 트랜잭션: 픽업 완료(점주 QR 확인)
    SALE_NEARBY = "sale_nearby"          # 발견: 내 주변 마감세일


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("order_id", "type", name="uq_notifications_order_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True, nullable=True)
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), index=True, nullable=True)
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type"), nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
