"""add products name trgm index

Revision ID: e8b3f61a2c47
Revises: d7f42a9c0e15
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e8b3f61a2c47'
down_revision: Union[str, Sequence[str], None] = 'd7f42a9c0e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    CONCURRENTLY строит индекс без блокировки записи в products, но не работает внутри транзакции.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_name_trgm "
            "ON products USING gin (name gin_trgm_ops)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
