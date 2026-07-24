"""add sale description and image_url

Revision ID: 640ad582d942
Revises: 338690ffff12
Create Date: 2026-07-24 20:55:13.097793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '640ad582d942'
down_revision: Union[str, Sequence[str], None] = '338690ffff12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sales', sa.Column('description', sa.String(length=1000), nullable=True))
    op.add_column('sales', sa.Column('image_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sales', 'image_url')
    op.drop_column('sales', 'description')
