"""add geocoding fields

Revision ID: a1b2c3d4e5f6
Revises: 35a374158af8
Create Date: 2025-01-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '35a374158af8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add geocoding columns to incident table
    op.add_column('incident', sa.Column('latitude', sa.Numeric(10, 8), nullable=True))
    op.add_column('incident', sa.Column('longitude', sa.Numeric(11, 8), nullable=True))
    op.add_column('incident', sa.Column('location_precision', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove geocoding columns
    op.drop_column('incident', 'location_precision')
    op.drop_column('incident', 'longitude')
    op.drop_column('incident', 'latitude')

