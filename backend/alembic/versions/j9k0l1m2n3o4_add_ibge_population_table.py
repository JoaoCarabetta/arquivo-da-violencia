"""add_ibge_population_table

Revision ID: j9k0l1m2n3o4
Revises: i8j9k0l1m2n3
Create Date: 2026-08-19 23:54:00.000000

Add IBGE population table to store cached population data for municipalities
and states, supporting rate per 100k calculations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'j9k0l1m2n3o4'
down_revision: Union[str, Sequence[str], None] = 'i8j9k0l1m2n3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ibge_population_exists(bind) -> bool:
    """Check if ibge_population table exists."""
    inspector = inspect(bind)
    return 'ibge_population' in inspector.get_table_names()


def _index_exists(bind, index_name: str, table_name: str) -> bool:
    """Check if an index exists on a table."""
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    """Create ibge_population table if it doesn't exist."""
    bind = op.get_bind()
    
    if not _ibge_population_exists(bind):
        op.create_table(
            'ibge_population',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code_muni', sa.Integer(), nullable=True),
            sa.Column('code_state', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True),
            sa.Column('name_muni', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
            sa.Column('name_state', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column('abbrev_state', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True),
            sa.Column('population', sa.Integer(), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_ibge_population_code_muni'), 'ibge_population', ['code_muni'], unique=False)
        op.create_index(op.f('ix_ibge_population_code_state'), 'ibge_population', ['code_state'], unique=False)
    else:
        # Table exists, ensure indexes exist
        if not _index_exists(bind, 'ix_ibge_population_code_muni', 'ibge_population'):
            op.create_index(op.f('ix_ibge_population_code_muni'), 'ibge_population', ['code_muni'], unique=False)
        if not _index_exists(bind, 'ix_ibge_population_code_state', 'ibge_population'):
            op.create_index(op.f('ix_ibge_population_code_state'), 'ibge_population', ['code_state'], unique=False)


def downgrade() -> None:
    """Drop ibge_population table."""
    op.drop_index(op.f('ix_ibge_population_code_state'), table_name='ibge_population')
    op.drop_index(op.f('ix_ibge_population_code_muni'), table_name='ibge_population')
    op.drop_table('ibge_population')
