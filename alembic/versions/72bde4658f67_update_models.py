"""update models

Revision ID: 72bde4658f67
Revises: 57e849c008eb
Create Date: 2026-04-11 16:47:17.627371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72bde4658f67'
down_revision: Union[str, Sequence[str], None] = '57e849c008eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # balance -> DECIMAL
    op.alter_column(
        'users',
        'balance',
        existing_type=sa.INTEGER(),
        type_=sa.DECIMAL(precision=10, scale=2),
        existing_nullable=False
    )

    # email: nullable=False (тип оставляем String(20), как в модели)
    op.alter_column(
        'users',
        'email',
        existing_type=sa.String(length=20),
        nullable=False
    )

    # age: nullable=False
    op.alter_column(
        'users',
        'age',
        existing_type=sa.INTEGER(),
        nullable=False
    )

    # order_items.quantity: nullable=False
    op.alter_column(
        'order_items',
        'quantity',
        existing_type=sa.INTEGER(),
        nullable=False
    )

    # server_default для created_at
    op.alter_column(
        'users',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()')
    )

    op.alter_column(
        'products',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()')
    )

    op.alter_column(
        'orders',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()')
    )

    op.alter_column(
        'reviews',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()')
    )


def downgrade() -> None:
    """Downgrade schema."""

    # откат server_default
    op.alter_column(
        'users',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=None
    )

    op.alter_column(
        'products',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=None
    )

    op.alter_column(
        'orders',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=None
    )

    op.alter_column(
        'reviews',
        'created_at',
        existing_type=sa.DateTime(),
        server_default=None
    )

    # order_items.quantity обратно nullable
    op.alter_column(
        'order_items',
        'quantity',
        existing_type=sa.INTEGER(),
        nullable=True
    )

    # age обратно nullable
    op.alter_column(
        'users',
        'age',
        existing_type=sa.INTEGER(),
        nullable=True
    )

    # email обратно nullable
    op.alter_column(
        'users',
        'email',
        existing_type=sa.String(length=20),
        nullable=True
    )

    # balance обратно в INTEGER
    op.alter_column(
        'users',
        'balance',
        existing_type=sa.DECIMAL(precision=10, scale=2),
        type_=sa.INTEGER(),
        existing_nullable=False
    )
