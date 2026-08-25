"""add_municipality_code_to_unique_event

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2026-08-25 12:30:00.000000

Add municipality_code field to unique_event table to store 7-digit IBGE
municipal codes for Brazilian municipalities (issue #174).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k0l1m2n3o4p5'
down_revision: Union[str, Sequence[str], None] = 'j9k0l1m2n3o4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add municipality_code field to unique_event."""
    op.add_column('unique_event', sa.Column('municipality_code', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_unique_event_municipality_code'), 'unique_event', ['municipality_code'], unique=False)


def downgrade() -> None:
    """Remove municipality_code field from unique_event."""
    op.drop_index(op.f('ix_unique_event_municipality_code'), table_name='unique_event')
    op.drop_column('unique_event', 'municipality_code')
