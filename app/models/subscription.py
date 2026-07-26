from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    min_discount_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    radius_m: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    receive_from: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    receive_to: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
