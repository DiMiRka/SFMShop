"""add order status

Revision ID: c5e81f3a9d02
Revises: a8d3e5b17c46
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e81f3a9d02'
down_revision: Union[str, Sequence[str], None] = 'a8d3e5b17c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Существующие заказы оплачивались при создании, поэтому получают статус paid.
    """
    op.add_column('orders', sa.Column('status', sa.String(length=20), nullable=False, server_default='paid'))
    op.alter_column('orders', 'status', server_default='pending')
    op.create_check_constraint(
        'check_order_status', 'orders', "status IN ('pending', 'paid', 'failed', 'cancelled')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('check_order_status', 'orders', type_='check')
    op.drop_column('orders', 'status')
