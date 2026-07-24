"""order refund: refunded status, refunded_at, order_refunded notif

Revision ID: b90aaf2c1cfb
Revises: 640ad582d942
Create Date: 2026-07-25 00:25:24.652176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b90aaf2c1cfb'
down_revision: Union[str, Sequence[str], None] = '640ad582d942'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "orders",
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    # enum 값 추가는 트랜잭션 밖에서(autocommit) — PG 제약 회피. 라벨은 enum NAME(대문자).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'REFUNDED'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ORDER_REFUNDED'")


def downgrade() -> None:
    """Downgrade schema."""
    # PG는 enum 값 제거를 지원하지 않는다(타입 재생성 필요) → 컬럼만 되돌린다.
    op.drop_column("orders", "refunded_at")
