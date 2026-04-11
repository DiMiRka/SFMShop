"""update models

Revision ID: 482b36f14519
Revises: 72bde4658f67
Create Date: 2026-04-11 18:16:29.921954

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '482b36f14519'
down_revision: Union[str, Sequence[str], None] = '72bde4658f67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # order_items
    op.drop_constraint('order_items_product_id_fkey', 'order_items', type_='foreignkey')
    op.drop_constraint('order_items_order_id_fkey', 'order_items', type_='foreignkey')

    op.create_foreign_key(
        'order_items_product_id_fkey',
        'order_items', 'products',
        ['product_id'], ['id'],
        onupdate='CASCADE', ondelete='CASCADE'
    )
    op.create_foreign_key(
        'order_items_order_id_fkey',
        'order_items', 'orders',
        ['order_id'], ['id'],
        onupdate='CASCADE', ondelete='CASCADE'
    )

    # orders
    op.drop_constraint('orders_user_id_fkey', 'orders', type_='foreignkey')
    op.create_foreign_key(
        'orders_user_id_fkey',
        'orders', 'users',
        ['user_id'], ['id'],
        onupdate='CASCADE', ondelete='CASCADE'
    )

    # reviews
    op.drop_constraint('reviews_user_id_fkey', 'reviews', type_='foreignkey')
    op.drop_constraint('reviews_product_id_fkey', 'reviews', type_='foreignkey')

    op.create_foreign_key(
        'reviews_product_id_fkey',
        'reviews', 'products',
        ['product_id'], ['id'],
        onupdate='CASCADE', ondelete='CASCADE'
    )
    op.create_foreign_key(
        'reviews_user_id_fkey',
        'reviews', 'users',
        ['user_id'], ['id'],
        onupdate='CASCADE', ondelete='CASCADE'
    )


def downgrade() -> None:
    # reviews
    op.drop_constraint('reviews_user_id_fkey', 'reviews', type_='foreignkey')
    op.drop_constraint('reviews_product_id_fkey', 'reviews', type_='foreignkey')

    op.create_foreign_key(
        'reviews_product_id_fkey',
        'reviews', 'products',
        ['product_id'], ['id']
    )
    op.create_foreign_key(
        'reviews_user_id_fkey',
        'reviews', 'users',
        ['user_id'], ['id']
    )

    # orders
    op.drop_constraint('orders_user_id_fkey', 'orders', type_='foreignkey')
    op.create_foreign_key(
        'orders_user_id_fkey',
        'orders', 'users',
        ['user_id'], ['id']
    )

    # order_items
    op.drop_constraint('order_items_order_id_fkey', 'order_items', type_='foreignkey')
    op.drop_constraint('order_items_product_id_fkey', 'order_items', type_='foreignkey')

    op.create_foreign_key(
        'order_items_order_id_fkey',
        'order_items', 'orders',
        ['order_id'], ['id']
    )
    op.create_foreign_key(
        'order_items_product_id_fkey',
        'order_items', 'products',
        ['product_id'], ['id']
    )
