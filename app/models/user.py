import enum

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class Role(str, enum.Enum):
    USER = "user"
    OWNER = "owner"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="user_role"), default=Role.USER, nullable=False
    )
