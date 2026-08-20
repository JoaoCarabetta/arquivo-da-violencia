"""Test idempotency of IBGE population migration."""
import pytest
from sqlalchemy import create_engine, inspect, MetaData, Table, Column, Integer, String, DateTime
from sqlalchemy.pool import StaticPool
from alembic import op
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
import sqlmodel

# Import the helper functions from the migration
import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent
alembic_versions_path = backend_path / "alembic" / "versions"
sys.path.insert(0, str(alembic_versions_path))

from j9k0l1m2n3o4_add_ibge_population_table import (
    _ibge_population_exists,
    _index_exists,
    upgrade as migration_upgrade
)


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture
def alembic_context(sqlite_engine):
    """Create an Alembic migration context for testing."""
    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        yield context, connection


def test_ibge_population_exists_when_table_missing(sqlite_engine):
    """Test _ibge_population_exists returns False when table doesn't exist."""
    with sqlite_engine.connect() as conn:
        assert not _ibge_population_exists(conn)


def test_ibge_population_exists_when_table_present(sqlite_engine):
    """Test _ibge_population_exists returns True when table exists."""
    # Create the table manually
    metadata = MetaData()
    Table(
        'ibge_population',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('population', Integer),
        Column('year', Integer),
        Column('source', String(100)),
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
    )
    metadata.create_all(sqlite_engine)
    
    with sqlite_engine.connect() as conn:
        assert _ibge_population_exists(conn)


def test_upgrade_creates_table_when_missing(sqlite_engine):
    """Test upgrade creates table when it doesn't exist."""
    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        
        # Patch op module to use our connection
        import alembic.op as op_module
        op_module._proxy = ops
        
        # Run upgrade
        migration_upgrade()
        
        # Verify table was created
        inspector = inspect(connection)
        assert 'ibge_population' in inspector.get_table_names()
        
        # Verify indexes were created
        indexes = inspector.get_indexes('ibge_population')
        index_names = [idx['name'] for idx in indexes]
        assert 'ix_ibge_population_code_muni' in index_names
        assert 'ix_ibge_population_code_state' in index_names


def test_upgrade_idempotent_when_table_exists(sqlite_engine):
    """Test upgrade doesn't fail when table already exists."""
    # First, create the table manually (simulating it was loaded without stamping)
    metadata = MetaData()
    Table(
        'ibge_population',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('code_muni', Integer),
        Column('code_state', String(2)),
        Column('name_muni', String(200)),
        Column('name_state', String(100)),
        Column('abbrev_state', String(2)),
        Column('population', Integer),
        Column('year', Integer),
        Column('source', String(100)),
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
    )
    metadata.create_all(sqlite_engine)
    
    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        
        # Patch op module to use our connection
        import alembic.op as op_module
        op_module._proxy = ops
        
        # Run upgrade - should not raise DuplicateTable error
        migration_upgrade()
        
        # Verify table still exists
        inspector = inspect(connection)
        assert 'ibge_population' in inspector.get_table_names()
        
        # Verify indexes were created (since we didn't create them manually)
        indexes = inspector.get_indexes('ibge_population')
        index_names = [idx['name'] for idx in indexes]
        assert 'ix_ibge_population_code_muni' in index_names
        assert 'ix_ibge_population_code_state' in index_names


def test_index_exists_helper(sqlite_engine):
    """Test _index_exists helper function."""
    metadata = MetaData()
    table = Table(
        'ibge_population',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('code_muni', Integer, index=True),
        Column('population', Integer),
        Column('year', Integer),
        Column('source', String(100)),
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
    )
    metadata.create_all(sqlite_engine)
    
    with sqlite_engine.connect() as conn:
        # The index should exist for code_muni
        inspector = inspect(conn)
        indexes = inspector.get_indexes('ibge_population')
        
        # Check that at least one index exists
        assert len(indexes) > 0
        
        # Test with non-existent index
        assert not _index_exists(conn, 'nonexistent_index', 'ibge_population')
