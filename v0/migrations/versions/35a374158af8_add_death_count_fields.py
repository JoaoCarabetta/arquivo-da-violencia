"""add death_count fields

Revision ID: 35a374158af8
Revises: b3036b471f88
Create Date: 2025-01-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35a374158af8'
down_revision: Union[str, None] = 'b3036b471f88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add death_count column to extracted_event table
    op.add_column('extracted_event', sa.Column('death_count', sa.Integer(), nullable=True))
    
    # Add death_count column to incident table
    op.add_column('incident', sa.Column('death_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove death_count columns
    op.drop_column('incident', 'death_count')
    op.drop_column('extracted_event', 'death_count')








