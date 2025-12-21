"""create events_ground_truth table

Revision ID: f34d35ecfc6d
Revises: a1b2c3d4e5f6
Create Date: 2025-01-20 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f34d35ecfc6d'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create events_ground_truth table with same structure as extracted_event plus group_id
    op.create_table(
        'events_ground_truth',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('extracted_date', sa.DateTime(), nullable=True),
        sa.Column('extracted_location', sa.String(length=256), nullable=True),
        sa.Column('extracted_victim_name', sa.String(length=256), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('death_count', sa.Integer(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incident.id'], ),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('events_ground_truth')

