"""add order_picked_up notification type

Revision ID: 40b1c02161d9
Revises: 4d7078914457
Create Date: 2026-07-23 11:02:03.174696

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '40b1c02161d9'
down_revision: Union[str, Sequence[str], None] = '4d7078914457'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # enum 값 추가는 트랜잭션 밖에서(autocommit) — PG 제약 회피. 라벨은 enum NAME(대문자).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'ORDER_PICKED_UP'")


def downgrade() -> None:
    """Downgrade schema."""
    # PG는 enum 값 제거를 지원하지 않는다(타입 재생성 필요) → no-op.
    pass
