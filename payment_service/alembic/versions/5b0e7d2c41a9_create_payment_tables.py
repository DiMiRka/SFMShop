"""create payment tables

Revision ID: 5b0e7d2c41a9
Revises:
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b0e7d2c41a9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'wallets',
        sa.Column('user_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('balance', sa.DECIMAL(precision=12, scale=2), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('balance >= 0', name='check_wallet_balance'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount > 0', name='check_payment_amount'),
        sa.CheckConstraint("status IN ('success', 'failed', 'refunded')", name='check_payment_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_payments_idempotency_key'),
    )
    op.create_index('ix_payments_order_id', 'payments', ['order_id'])
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index(
        'uq_payments_order_success', 'payments', ['order_id'], unique=True,
        postgresql_where=sa.text("status = 'success'"),
    )
    op.create_table(
        'wallet_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount <> 0', name='check_transaction_amount'),
        sa.CheckConstraint("kind IN ('top_up', 'charge', 'refund')", name='check_transaction_kind'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.ForeignKeyConstraint(['user_id'], ['wallets.user_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_wallet_transactions_idempotency_key'),
    )
    op.create_index('ix_wallet_transactions_user_id', 'wallet_transactions', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_wallet_transactions_user_id', table_name='wallet_transactions')
    op.drop_table('wallet_transactions')
    op.drop_index('uq_payments_order_success', table_name='payments', postgresql_where=sa.text("status = 'success'"))
    op.drop_index('ix_payments_user_id', table_name='payments')
    op.drop_index('ix_payments_order_id', table_name='payments')
    op.drop_table('payments')
    op.drop_table('wallets')
