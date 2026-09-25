"""Test idempotency of municipality_code UniqueEvent migration (k0l1…)."""
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect
from sqlalchemy.pool import StaticPool

backend_path = Path(__file__).parent.parent
alembic_versions_path = backend_path / "alembic" / "versions"
sys.path.insert(0, str(alembic_versions_path))

from k0l1m2n3o4p5_add_municipality_code_to_unique_event import (  # noqa: E402
    _INDEX_NAME,
    _column_exists,
    _index_exists,
    upgrade as migration_upgrade,
)


@pytest.fixture
def sqlite_engine():
    """Create an in-memory SQLite engine for testing."""
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_unique_event_table(engine, *, with_municipality_code: bool = False):
    """Minimal unique_event stand-in for migration tests."""
    metadata = MetaData()
    columns = [
        Column("id", Integer, primary_key=True),
        Column("city", String(100)),
        Column("state", String(50)),
    ]
    if with_municipality_code:
        columns.append(Column("municipality_code", Integer, index=True))
    Table("unique_event", metadata, *columns)
    metadata.create_all(engine)


def test_column_exists_helpers(sqlite_engine):
    _create_unique_event_table(sqlite_engine, with_municipality_code=False)
    with sqlite_engine.connect() as conn:
        assert not _column_exists(conn, "unique_event", "municipality_code")
        assert not _index_exists(conn, _INDEX_NAME, "unique_event")
        assert not _index_exists(conn, "nonexistent_index", "unique_event")

    engine_with_col = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_unique_event_table(engine_with_col, with_municipality_code=True)
    with engine_with_col.connect() as conn:
        assert _column_exists(conn, "unique_event", "municipality_code")


def test_upgrade_creates_column_when_missing(sqlite_engine):
    _create_unique_event_table(sqlite_engine, with_municipality_code=False)

    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        import alembic.op as op_module

        op_module._proxy = ops
        migration_upgrade()

        inspector = inspect(connection)
        col_names = [c["name"] for c in inspector.get_columns("unique_event")]
        assert "municipality_code" in col_names
        index_names = [idx["name"] for idx in inspector.get_indexes("unique_event")]
        assert _INDEX_NAME in index_names


def test_upgrade_idempotent_when_column_and_index_exist(sqlite_engine):
    """Simulate prod ops SQL: column + index already present before alembic."""
    _create_unique_event_table(sqlite_engine, with_municipality_code=False)

    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        import alembic.op as op_module

        op_module._proxy = ops

        # Ops-style apply (column + named index), then alembic upgrade
        ops.add_column(
            "unique_event",
            Column("municipality_code", Integer(), nullable=True),
        )
        ops.create_index(_INDEX_NAME, "unique_event", ["municipality_code"], unique=False)

        migration_upgrade()  # must not raise DuplicateColumn / DuplicateIndex

        inspector = inspect(connection)
        col_names = [c["name"] for c in inspector.get_columns("unique_event")]
        assert "municipality_code" in col_names
        index_names = [idx["name"] for idx in inspector.get_indexes("unique_event")]
        assert _INDEX_NAME in index_names


def test_upgrade_adds_index_when_only_column_exists(sqlite_engine):
    """Column present, index missing — upgrade should only create the index."""
    metadata = MetaData()
    Table(
        "unique_event",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("municipality_code", Integer),  # no index=
    )
    metadata.create_all(sqlite_engine)

    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        import alembic.op as op_module

        op_module._proxy = ops
        assert _column_exists(connection, "unique_event", "municipality_code")
        assert not _index_exists(connection, _INDEX_NAME, "unique_event")

        migration_upgrade()

        assert _index_exists(connection, _INDEX_NAME, "unique_event")
