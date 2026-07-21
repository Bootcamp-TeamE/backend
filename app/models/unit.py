import enum

from sqlalchemy import Boolean, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class UnitType(str, enum.Enum):
    COUNT = "count"
    WEIGHT = "weight"


class Unit(Base, TimestampMixin):
    """판매 단위 마스터. enum 대신 참조 테이블 — 새 단위는 row 추가만."""

    __tablename__ = "units"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_type: Mapped[UnitType] = mapped_column(SAEnum(UnitType, name="unit_type"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
