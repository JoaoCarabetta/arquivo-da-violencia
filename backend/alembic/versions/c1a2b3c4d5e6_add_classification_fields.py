"""add_classification_fields

Revision ID: c1a2b3c4d5e6
Revises: 8d67cac08016
Create Date: 2025-12-21 12:00:00.000000

This migration:
1. Adds classification fields (is_violent_death, classification_confidence, classification_reasoning)
2. Migrates status values from old names to new descriptive names
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '8d67cac08016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add classification fields and migrate status values."""
    
    # Add new classification columns
    with op.batch_alter_table('source_google_news', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_violent_death', sa.Boolean(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('classification_confidence', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column('classification_reasoning', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_source_google_news_is_violent_death'), 
            ['is_violent_death'], 
            unique=False
        )
    
    # Migrate existing status values to new names (using underscores for SQLAlchemy enum compatibility)
    # Old: pending, downloaded, processed, failed, ignored
    # New: ready_for_classification, ready_for_download, ready_for_extraction, 
    #      extracted, failed_in_download, failed_in_extraction, discarded
    
    conn = op.get_bind()
    
    # Map old status values to new ones
    # pending -> ready_for_classification (needs classification)
    # downloaded -> ready_for_extraction (already downloaded, skip to extraction)
    # processed -> extracted
    # failed -> failed_in_download (most common failure point)
    # ignored -> discarded
    
    conn.execute(sa.text("""
        UPDATE source_google_news 
        SET status = CASE status
            WHEN 'pending' THEN 'ready_for_classification'
            WHEN 'downloaded' THEN 'ready_for_extraction'
            WHEN 'processed' THEN 'extracted'
            WHEN 'failed' THEN 'failed_in_download'
            WHEN 'ignored' THEN 'discarded'
            ELSE status
        END
    """))


def downgrade() -> None:
    """Remove classification fields and revert status values."""
    
    conn = op.get_bind()
    
    # Revert status values to old names
    conn.execute(sa.text("""
        UPDATE source_google_news 
        SET status = CASE status
            WHEN 'ready_for_classification' THEN 'pending'
            WHEN 'ready_for_download' THEN 'pending'
            WHEN 'ready_for_extraction' THEN 'downloaded'
            WHEN 'extracted' THEN 'processed'
            WHEN 'failed_in_download' THEN 'failed'
            WHEN 'failed_in_extraction' THEN 'failed'
            WHEN 'discarded' THEN 'ignored'
            ELSE status
        END
    """))
    
    # Remove classification columns
    with op.batch_alter_table('source_google_news', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_source_google_news_is_violent_death'))
        batch_op.drop_column('classification_reasoning')
        batch_op.drop_column('classification_confidence')
        batch_op.drop_column('is_violent_death')

