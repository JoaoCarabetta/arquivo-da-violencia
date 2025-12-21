"""add_deduplication_enrichment_fields

Revision ID: d2e3f4g5h6i7
Revises: c1a2b3c4d5e6
Create Date: 2025-12-21 18:00:00.000000

This migration:
1. Adds deduplication_status to raw_event
2. Adds enrichment fields to unique_event (needs_enrichment, last_enriched_at, enrichment_model)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4g5h6i7'
down_revision: Union[str, Sequence[str], None] = 'c1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deduplication and enrichment fields."""
    
    # Add deduplication_status to raw_event
    with op.batch_alter_table('raw_event', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('deduplication_status', sqlmodel.sql.sqltypes.AutoString(length=20), 
                      nullable=False, server_default='pending')
        )
        batch_op.create_index(
            batch_op.f('ix_raw_event_deduplication_status'), 
            ['deduplication_status'], 
            unique=False
        )
    
    # Add enrichment fields to unique_event
    with op.batch_alter_table('unique_event', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('needs_enrichment', sa.Boolean(), nullable=False, server_default='1')
        )
        batch_op.add_column(
            sa.Column('last_enriched_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('enrichment_model', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_unique_event_needs_enrichment'), 
            ['needs_enrichment'], 
            unique=False
        )


def downgrade() -> None:
    """Remove deduplication and enrichment fields."""
    
    # Remove enrichment fields from unique_event
    with op.batch_alter_table('unique_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_unique_event_needs_enrichment'))
        batch_op.drop_column('enrichment_model')
        batch_op.drop_column('last_enriched_at')
        batch_op.drop_column('needs_enrichment')
    
    # Remove deduplication_status from raw_event
    with op.batch_alter_table('raw_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_raw_event_deduplication_status'))
        batch_op.drop_column('deduplication_status')

