import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class SaleStatus(str, enum.Enum):
    ACTIVE = "active"
    SOLDOUT = "soldout"
    CLOSED = "closed"


class Sale(Base, TimestampMixin):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True, nullable=False)
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    normal_price: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_code: Mapped[str] = mapped_column(ForeignKey("units.code"), index=True, nullable=False)
    min_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[SaleStatus] = mapped_column(
        SAEnum(SaleStatus, name="sale_status"), default=SaleStatus.ACTIVE, index=True, nullable=False
    )
