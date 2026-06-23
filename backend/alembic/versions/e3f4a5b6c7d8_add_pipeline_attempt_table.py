"""add_pipeline_attempt_table

Revision ID: e3f4a5b6c7d8
Revises: 43705696cb2c
Create Date: 2026-06-23 16:05:00.000000

This migration adds the pipeline_attempt diagnostics table, which records one row
per download/extraction stage attempt (success or failure) with a classified
failure reason and context (http_status, url_domain, model, content_length,
duration). It is the backbone for analyzing pipeline failures over time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = '43705696cb2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the pipeline_attempt table."""
    op.create_table(
        'pipeline_attempt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_google_news_id', sa.Integer(), nullable=True),
        sa.Column('raw_event_id', sa.Integer(), nullable=True),
        sa.Column('stage', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('failure_reason', sqlmodel.sql.sqltypes.AutoString(length=40), nullable=True),
        sa.Column('failure_detail', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('url_domain', sqlmodel.sql.sqltypes.AutoString(length=256), nullable=True),
        sa.Column('model', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('content_length', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['source_google_news_id'], ['source_google_news.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pipeline_attempt_source_google_news_id'), 'pipeline_attempt', ['source_google_news_id'], unique=False)
    op.create_index(op.f('ix_pipeline_attempt_raw_event_id'), 'pipeline_attempt', ['raw_event_id'], unique=False)
    op.create_index(op.f('ix_pipeline_attempt_stage'), 'pipeline_attempt', ['stage'], unique=False)
    op.create_index(op.f('ix_pipeline_attempt_outcome'), 'pipeline_attempt', ['outcome'], unique=False)
    op.create_index(op.f('ix_pipeline_attempt_failure_reason'), 'pipeline_attempt', ['failure_reason'], unique=False)
    op.create_index(op.f('ix_pipeline_attempt_url_domain'), 'pipeline_attempt', ['url_domain'], unique=False)
    op.create_index(op.f('ix_pipeline_attempt_created_at'), 'pipeline_attempt', ['created_at'], unique=False)


def downgrade() -> None:
    """Drop the pipeline_attempt table."""
    op.drop_index(op.f('ix_pipeline_attempt_created_at'), table_name='pipeline_attempt')
    op.drop_index(op.f('ix_pipeline_attempt_url_domain'), table_name='pipeline_attempt')
    op.drop_index(op.f('ix_pipeline_attempt_failure_reason'), table_name='pipeline_attempt')
    op.drop_index(op.f('ix_pipeline_attempt_outcome'), table_name='pipeline_attempt')
    op.drop_index(op.f('ix_pipeline_attempt_stage'), table_name='pipeline_attempt')
    op.drop_index(op.f('ix_pipeline_attempt_raw_event_id'), table_name='pipeline_attempt')
    op.drop_index(op.f('ix_pipeline_attempt_source_google_news_id'), table_name='pipeline_attempt')
    op.drop_table('pipeline_attempt')
