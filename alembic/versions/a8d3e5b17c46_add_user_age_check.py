"""add user age check

Revision ID: a8d3e5b17c46
Revises: f1c7d2a8e905
Create Date: 2026-10-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a8d3e5b17c46'
down_revision: Union[str, Sequence[str], None] = 'f1c7d2a8e905'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Упадёт, если в таблице уже есть пользователь младше 18 лет.
    """
    op.create_check_constraint('check_user_age', 'users', 'age >= 18')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('check_user_age', 'users', type_='check')
