from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class Store(Base, TimestampMixin):
    """매장. 시드 매장은 점주·시장 미확정이라 owner_id·market_id nullable."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), index=True, nullable=True)
    # 1계정=1매장: owner_id는 유일(UNIQUE). NULL은 여러 개 허용(점주 미확정 시드).
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, unique=True, nullable=True
    )
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
