"""add marketplace listings

Revision ID: 5d2a9f7c3e81
Revises: 0b6d4e2f8a13
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d2a9f7c3e81'
down_revision: Union[str, Sequence[str], None] = '0b6d4e2f8a13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'marketplace_listings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('marketplace', sa.String(length=20), nullable=False),
        sa.Column('offer_id', sa.String(length=100), nullable=False),
        sa.Column('external_product_id', sa.BigInteger(), nullable=True),
        sa.Column('external_size_id', sa.BigInteger(), nullable=True),
        sa.Column('synced_quantity', sa.Integer(), nullable=True),
        sa.Column('synced_price', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE', onupdate='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('marketplace', 'offer_id', name='uq_marketplace_listings_offer'),
        sa.UniqueConstraint('marketplace', 'product_id', name='uq_marketplace_listings_product'),
    )
    op.create_index('ix_marketplace_listings_product_id', 'marketplace_listings', ['product_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_marketplace_listings_product_id', table_name='marketplace_listings')
    op.drop_table('marketplace_listings')
