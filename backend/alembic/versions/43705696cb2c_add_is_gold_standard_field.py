"""add_is_gold_standard_field

Revision ID: 43705696cb2c
Revises: d2e3f4g5h6i7
Create Date: 2025-12-21 17:38:04.392976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '43705696cb2c'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4g5h6i7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add is_gold_standard column with default False
    op.add_column('raw_event', sa.Column('is_gold_standard', sa.Boolean(), nullable=False, server_default='0'))
    
    # Add index for efficient filtering
    op.create_index(op.f('ix_raw_event_is_gold_standard'), 'raw_event', ['is_gold_standard'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index
    op.drop_index(op.f('ix_raw_event_is_gold_standard'), table_name='raw_event')
    
    # Drop column
    op.drop_column('raw_event', 'is_gold_standard')

