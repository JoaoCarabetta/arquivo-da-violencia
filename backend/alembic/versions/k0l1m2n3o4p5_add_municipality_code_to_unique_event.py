"""add_municipality_code_to_unique_event

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2026-08-25 12:30:00.000000

Add municipality_code field to unique_event table to store 7-digit IBGE
municipal codes for Brazilian municipalities (issue #174).

Idempotent: prod may already have the column/index from an ops SQL apply
before alembic caught up (geocode remmediate 2026-09-25).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'k0l1m2n3o4p5'
down_revision: Union[str, Sequence[str], None] = 'j9k0l1m2n3o4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = 'ix_unique_event_municipality_code'


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)


def _index_exists(bind, index_name: str, table_name: str) -> bool:
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    """Add municipality_code field to unique_event if missing."""
    bind = op.get_bind()

    if not _column_exists(bind, 'unique_event', 'municipality_code'):
        op.add_column('unique_event', sa.Column('municipality_code', sa.Integer(), nullable=True))

    if not _index_exists(bind, _INDEX_NAME, 'unique_event'):
        op.create_index(op.f(_INDEX_NAME), 'unique_event', ['municipality_code'], unique=False)


def downgrade() -> None:
    """Remove municipality_code field from unique_event if present."""
    bind = op.get_bind()

    if _index_exists(bind, _INDEX_NAME, 'unique_event'):
        op.drop_index(op.f(_INDEX_NAME), table_name='unique_event')

    if _column_exists(bind, 'unique_event', 'municipality_code'):
        op.drop_column('unique_event', 'municipality_code')
