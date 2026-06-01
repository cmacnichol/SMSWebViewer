"""add expires_at to api_tokens

Revision ID: b3f29a1c8e7d
Revises: a85115d10dba
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f29a1c8e7d'
down_revision: Union[str, Sequence[str], None] = 'a85115d10dba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional expires_at column to api_tokens table."""
    op.add_column(
        'api_tokens',
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove expires_at column from api_tokens table."""
    op.drop_column('api_tokens', 'expires_at')
