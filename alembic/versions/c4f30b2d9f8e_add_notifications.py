"""add notifications to app_config

Revision ID: c4f30b2d9f8e
Revises: b3f29a1c8e7d
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f30b2d9f8e'
down_revision: Union[str, Sequence[str], None] = 'b3f29a1c8e7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add notification columns to app_config."""
    op.add_column('app_config', sa.Column('notification_urls', sa.Text(), nullable=True))
    op.add_column('app_config', sa.Column('notify_on_success', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('app_config', sa.Column('notify_on_failure', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    """Remove notification columns from app_config."""
    op.drop_column('app_config', 'notify_on_failure')
    op.drop_column('app_config', 'notify_on_success')
    op.drop_column('app_config', 'notification_urls')
