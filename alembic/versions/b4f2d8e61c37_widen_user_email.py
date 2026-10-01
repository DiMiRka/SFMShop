"""widen user email

Revision ID: b4f2d8e61c37
Revises: 7a1e3c9d5b20
Create Date: 2026-10-01 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f2d8e61c37'
down_revision: Union[str, Sequence[str], None] = '7a1e3c9d5b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('users', 'email',
                    existing_type=sa.String(length=20),
                    type_=sa.String(length=255),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema.

    Упадёт, если в таблице уже есть email длиннее 20 символов.
    """
    op.alter_column('users', 'email',
                    existing_type=sa.String(length=255),
                    type_=sa.String(length=20),
                    existing_nullable=False)
