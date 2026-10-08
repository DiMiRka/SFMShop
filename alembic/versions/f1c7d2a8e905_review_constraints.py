"""review constraints

Revision ID: f1c7d2a8e905
Revises: e3a9c1f04b72
Create Date: 2026-10-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1c7d2a8e905'
down_revision: Union[str, Sequence[str], None] = 'e3a9c1f04b72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Упадёт, если в таблице уже есть два отзыва одного пользователя на один товар или оценка вне 1..5.
    """
    op.create_unique_constraint('uq_reviews_product_user', 'reviews', ['product_id', 'user_id'])
    op.create_check_constraint('check_review_rating', 'reviews', 'rating >= 1 AND rating <= 5')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('check_review_rating', 'reviews', type_='check')
    op.drop_constraint('uq_reviews_product_user', 'reviews', type_='unique')
