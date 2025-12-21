"""add victims and structured location fields

Revision ID: b3036b471f88
Revises: aaae58ed83fd
Create Date: 2025-12-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3036b471f88'
down_revision: Union[str, None] = 'aaae58ed83fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns
    op.add_column('incident', sa.Column('victims', sa.Text(), nullable=True))
    op.add_column('incident', sa.Column('country', sa.String(length=100), nullable=True))
    op.add_column('incident', sa.Column('state', sa.String(length=100), nullable=True))
    op.add_column('incident', sa.Column('street', sa.String(length=256), nullable=True))
    op.add_column('incident', sa.Column('location_extra_info', sa.Text(), nullable=True))
    
    # Drop old location column
    op.drop_column('incident', 'location')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add location column
    op.add_column('incident', sa.Column('location', sa.String(length=256), nullable=True))
    
    # Remove new columns
    op.drop_column('incident', 'location_extra_info')
    op.drop_column('incident', 'street')
    op.drop_column('incident', 'state')
    op.drop_column('incident', 'country')
    op.drop_column('incident', 'victims')

