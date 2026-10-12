"""add order payment id, drop user balance

Revision ID: d7f42a9c0e15
Revises: c5e81f3a9d02
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7f42a9c0e15'
down_revision: Union[str, Sequence[str], None] = 'c5e81f3a9d02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Баланс пользователя хранится в payment-service, заказ ссылается на свой платёж.
    """
    op.add_column('orders', sa.Column('payment_id', sa.Integer(), nullable=True))
    op.drop_column('users', 'balance')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('balance', sa.DECIMAL(precision=10, scale=2), server_default='0', nullable=False))
    op.alter_column('users', 'balance', server_default=None)
    op.drop_column('orders', 'payment_id')
