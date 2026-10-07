"""widen product name

Revision ID: e3a9c1f04b72
Revises: b4f2d8e61c37
Create Date: 2026-10-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3a9c1f04b72'
down_revision: Union[str, Sequence[str], None] = 'b4f2d8e61c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('products', 'name',
                    existing_type=sa.String(length=20),
                    type_=sa.String(length=200),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema.

    Упадёт, если в таблице уже есть название товара длиннее 20 символов.
    """
    op.alter_column('products', 'name',
                    existing_type=sa.String(length=200),
                    type_=sa.String(length=20),
                    existing_nullable=False)
