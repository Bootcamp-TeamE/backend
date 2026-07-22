from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class NotificationLog(Base, TimestampMixin):
    """발견 fanout 알림 발송 이력. UNIQUE(sale_id, user_id)가 멱등 발송 가드다."""

    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("sale_id", "user_id", name="uq_notification_log_sale_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
