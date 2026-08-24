"""add_country_field_to_source_and_raw_event

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
Create Date: 2026-08-19 23:00:00.000000

Add country field to source_google_news and raw_event tables to support
multi-country ingestion (BR, CL) and stop hardcoding "Brasil" in UniqueEvent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'i8j9k0l1m2n3'
down_revision: Union[str, Sequence[str], None] = 'h7i8j9k0l1m2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add country field to source_google_news and raw_event."""
    # Add country to source_google_news
    op.add_column('source_google_news', sa.Column('country', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True))
    op.create_index(op.f('ix_source_google_news_country'), 'source_google_news', ['country'], unique=False)
    
    # Backfill existing source_google_news records with BR
    op.execute("UPDATE source_google_news SET country = 'BR' WHERE country IS NULL")
    
    # Add country to raw_event
    op.add_column('raw_event', sa.Column('country', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True))
    op.create_index(op.f('ix_raw_event_country'), 'raw_event', ['country'], unique=False)
    
    # Backfill existing raw_event records with BR
    op.execute("UPDATE raw_event SET country = 'BR' WHERE country IS NULL")


def downgrade() -> None:
    """Remove country field from source_google_news and raw_event."""
    # Drop from raw_event
    op.drop_index(op.f('ix_raw_event_country'), table_name='raw_event')
    op.drop_column('raw_event', 'country')
    
    # Drop from source_google_news
    op.drop_index(op.f('ix_source_google_news_country'), table_name='source_google_news')
    op.drop_column('source_google_news', 'country')
