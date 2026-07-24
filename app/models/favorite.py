from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class Favorite(Base, TimestampMixin):
    """관심 매장(즐겨찾기). 유저-매장 1쌍은 유일."""

    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "store_id", name="uq_favorites_user_store"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True, nullable=False)
