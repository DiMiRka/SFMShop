"""add marketplace orders

Revision ID: 9c4e1b7d2f60
Revises: 5d2a9f7c3e81
Create Date: 2026-10-29 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9c4e1b7d2f60'
down_revision: Union[str, Sequence[str], None] = '5d2a9f7c3e81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'marketplace_orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('marketplace', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('total', sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('imported_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('marketplace', 'external_id', name='uq_marketplace_orders_external'),
    )
    op.create_index('ix_marketplace_orders_ordered_at', 'marketplace_orders', ['marketplace', 'ordered_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_marketplace_orders_ordered_at', table_name='marketplace_orders')
    op.drop_table('marketplace_orders')
