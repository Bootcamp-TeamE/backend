from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class Category(Base, TimestampMixin):
    """업종 마스터. enum 대신 참조 테이블 — 새 업종은 row 추가만."""

    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
