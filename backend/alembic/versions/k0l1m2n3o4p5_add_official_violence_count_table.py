"""add_official_violence_count_table

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2026-08-25 12:35:00.000000

Add official_violence_count table to store monthly victim counts from Ministry
of Justice VDE (Validador de Dados Estatísticos) for coverage comparison.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'k0l1m2n3o4p5'
down_revision: Union[str, Sequence[str], None] = 'j9k0l1m2n3o4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _official_violence_count_exists(bind) -> bool:
    """Check if official_violence_count table exists."""
    inspector = inspect(bind)
    return 'official_violence_count' in inspector.get_table_names()

def _index_exists(bind, index_name: str, table_name: str) -> bool:
    """Check if an index exists on a table."""
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)

def upgrade() -> None:
    """Create official_violence_count table if it doesn't exist."""
    bind = op.get_bind()

    if not _official_violence_count_exists(bind):
        op.create_table(
            'official_violence_count',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code_muni', sa.Integer(), nullable=False),
            sa.Column('year_month', sqlmodel.sql.sqltypes.AutoString(length=7), nullable=False),
            sa.Column('indicator', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
            sa.Column('victim_count', sa.Integer(), nullable=False),
            sa.Column('is_total', sa.Boolean(), nullable=False),
            sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code_muni', 'year_month', 'indicator', name='uq_official_violence_key')
        )
        op.create_index(op.f('ix_official_violence_count_code_muni'), 'official_violence_count', ['code_muni'], unique=False)
        op.create_index(op.f('ix_official_violence_count_year_month'), 'official_violence_count', ['year_month'], unique=False)
        op.create_index(op.f('ix_official_violence_count_indicator'), 'official_violence_count', ['indicator'], unique=False)
    else:
        # Table exists, ensure indexes and unique constraint exist
        if not _index_exists(bind, 'ix_official_violence_count_code_muni', 'official_violence_count'):
            op.create_index(op.f('ix_official_violence_count_code_muni'), 'official_violence_count', ['code_muni'], unique=False)
        if not _index_exists(bind, 'ix_official_violence_count_year_month', 'official_violence_count'):
            op.create_index(op.f('ix_official_violence_count_year_month'), 'official_violence_count', ['year_month'], unique=False)
        if not _index_exists(bind, 'ix_official_violence_count_indicator', 'official_violence_count'):
            op.create_index(op.f('ix_official_violence_count_indicator'), 'official_violence_count', ['indicator'], unique=False)

        # Add unique constraint if it doesn't exist
        inspector = inspect(bind)
        constraints = inspector.get_unique_constraints('official_violence_count')
        has_unique = any(
            set(c['column_names']) == {'code_muni', 'year_month', 'indicator'}
            for c in constraints
        )
        if not has_unique:
            op.create_unique_constraint('uq_official_violence_key', 'official_violence_count',
                                       ['code_muni', 'year_month', 'indicator'])

def downgrade() -> None:
    """Drop official_violence_count table."""
    bind = op.get_bind()

    # Drop unique constraint if it exists
    inspector = inspect(bind)
    if _official_violence_count_exists(bind):
        constraints = inspector.get_unique_constraints('official_violence_count')
        if any(c.get('name') == 'uq_official_violence_key' for c in constraints):
            op.drop_constraint('uq_official_violence_key', 'official_violence_count', type_='unique')

    op.drop_index(op.f('ix_official_violence_count_indicator'), table_name='official_violence_count')
    op.drop_index(op.f('ix_official_violence_count_year_month'), table_name='official_violence_count')
    op.drop_index(op.f('ix_official_violence_count_code_muni'), table_name='official_violence_count')
    op.drop_table('official_violence_count')
