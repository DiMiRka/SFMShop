"""add product description and embeddings

Revision ID: 0b6d4e2f8a13
Revises: e8b3f61a2c47
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR


# revision identifiers, used by Alembic.
revision: str = '0b6d4e2f8a13'
down_revision: Union[str, Sequence[str], None] = 'e8b3f61a2c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        'product_embeddings',
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('embedding', VECTOR(1536), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE', onupdate='CASCADE'),
        sa.PrimaryKeyConstraint('product_id'),
    )
    op.create_index(
        'ix_product_embeddings_embedding_hnsw', 'product_embeddings', ['embedding'],
        postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_product_embeddings_embedding_hnsw', table_name='product_embeddings')
    op.drop_table('product_embeddings')
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.drop_column('products', 'description')
