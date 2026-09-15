"""Issue #252/#254: OfficialSourceId/OfficialRevision must use VARCHAR, not PG native enums.

Issue #254: enum columns with DEFAULT block DROP TYPE unless migration drops defaults first.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, String, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import StaticPool
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
from sqlmodel import select

from app.models.official_violence_data import (
    OfficialRevision,
    OfficialSourceId,
    OfficialViolenceCount,
)

backend_path = Path(__file__).parent.parent
alembic_versions_path = backend_path / "alembic" / "versions"
sys.path.insert(0, str(alembic_versions_path))

from n3o4p5q6r7s8_fix_postgres_official_enum_varchar import upgrade as safety_upgrade


def test_official_violence_count_columns_use_varchar_not_native_enum():
    """SQLModel must not emit native Postgres ENUM types for source_id/revision."""
    source_col = OfficialViolenceCount.__table__.c.source_id
    revision_col = OfficialViolenceCount.__table__.c.revision

    assert isinstance(source_col.type, String)
    assert isinstance(revision_col.type, String)
    assert source_col.type.length >= 9  # longest value: validador
    assert revision_col.type.length >= 11  # longest value: consolidado
    assert not isinstance(source_col.type, postgresql.ENUM)
    assert not isinstance(revision_col.type, postgresql.ENUM)


@pytest.mark.asyncio
async def test_official_source_revision_lowercase_roundtrip(async_session):
    """Lowercase enum values must persist and load as Python enums."""
    row = OfficialViolenceCount(
        code_muni=3550308,
        year_month="2025-09",
        indicator="homicidio_doloso",
        source_id=OfficialSourceId.RJ,
        revision=OfficialRevision.PRELIMINAR,
        victim_count=7,
        is_total=False,
        source="test",
    )
    async_session.add(row)
    await async_session.commit()
    await async_session.refresh(row)

    assert row.source_id == OfficialSourceId.RJ
    assert row.source_id == "rj"
    assert row.revision == OfficialRevision.PRELIMINAR
    assert row.revision == "preliminar"

    result = await async_session.execute(
        select(OfficialViolenceCount).where(OfficialViolenceCount.id == row.id)
    )
    loaded = result.scalar_one()
    assert loaded.source_id == OfficialSourceId.RJ
    assert loaded.revision == OfficialRevision.PRELIMINAR


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


def test_safety_migration_noop_on_sqlite(sqlite_engine):
    """Safety migration is a no-op on SQLite (no PG enum types)."""
    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)

        import alembic.op as op_module

        op_module._proxy = ops
        safety_upgrade()  # should not raise


def test_safety_migration_noop_when_varchar_columns_exist(sqlite_engine):
    """Safety migration is a no-op when columns are already VARCHAR (clean DB)."""
    with sqlite_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE official_violence_count (
                    id INTEGER PRIMARY KEY,
                    source_id VARCHAR(20) NOT NULL DEFAULT 'validador',
                    revision VARCHAR(20) NOT NULL DEFAULT 'consolidado'
                )
                """
            )
        )

    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)

        import alembic.op as op_module

        op_module._proxy = ops
        safety_upgrade()

        cols = {c["name"]: c for c in inspect(connection).get_columns("official_violence_count")}
        assert "varchar" in str(cols["source_id"]["type"]).lower()
        assert "varchar" in str(cols["revision"]["type"]).lower()


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _postgres_engine_or_skip():
    import os

    candidates = []
    if os.environ.get("DATABASE_URL"):
        candidates.append(_normalize_postgres_url(os.environ["DATABASE_URL"]))
    candidates.extend(
        _normalize_postgres_url(f"postgresql://arquivo:arquivo_dev@{host}:5432/arquivo_dev")
        for host in ("postgres", "localhost")
    )

    for db_url in candidates:
        try:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception:
            continue
    pytest.skip("Postgres not available for enum conversion test")


def test_safety_migration_converts_postgres_enums():
    """Enum columns with DEFAULT must migrate without manual DROP DEFAULT dance (#254)."""
    engine = _postgres_engine_or_skip()
    conn = engine.connect()
    trans = conn.begin()
    try:
        conn.execute(text("DROP TABLE IF EXISTS official_violence_count CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS officialsourceid"))
        conn.execute(text("DROP TYPE IF EXISTS officialrevision"))
        conn.execute(
            text(
                "CREATE TYPE officialsourceid AS ENUM "
                "('VALIDADOR', 'RJ', 'MG', 'SP')"
            )
        )
        conn.execute(
            text(
                "CREATE TYPE officialrevision AS ENUM "
                "('PRELIMINAR', 'CONSOLIDADO')"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE official_violence_count (
                    id SERIAL PRIMARY KEY,
                    source_id officialsourceid NOT NULL DEFAULT 'VALIDADOR',
                    revision officialrevision NOT NULL DEFAULT 'CONSOLIDADO'
                )
                """
            )
        )
        conn.execute(text("INSERT INTO official_violence_count DEFAULT VALUES"))
        conn.execute(
            text(
                """
                INSERT INTO official_violence_count (source_id, revision)
                VALUES ('RJ'::officialsourceid, 'PRELIMINAR'::officialrevision)
                """
            )
        )

        context = MigrationContext.configure(conn)
        ops = Operations(context)

        import alembic.op as op_module

        op_module._proxy = ops
        safety_upgrade()

        source_type = conn.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'official_violence_count'
                  AND column_name = 'source_id'
                """
            )
        ).one()
        revision_type = conn.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'official_violence_count'
                  AND column_name = 'revision'
                """
            )
        ).one()

        assert source_type.data_type == "character varying"
        assert revision_type.data_type == "character varying"

        source_default = conn.execute(
            text(
                """
                SELECT column_default
                FROM information_schema.columns
                WHERE table_name = 'official_violence_count'
                  AND column_name = 'source_id'
                """
            )
        ).scalar()
        revision_default = conn.execute(
            text(
                """
                SELECT column_default
                FROM information_schema.columns
                WHERE table_name = 'official_violence_count'
                  AND column_name = 'revision'
                """
            )
        ).scalar()
        assert "validador" in source_default
        assert "consolidado" in revision_default

        source_enum = conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'officialsourceid'")
        ).scalar()
        revision_enum = conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'officialrevision'")
        ).scalar()
        assert source_enum is None
        assert revision_enum is None

        rows = conn.execute(
            text("SELECT source_id, revision FROM official_violence_count ORDER BY id")
        ).all()
        assert rows == [("validador", "consolidado"), ("rj", "preliminar")]
    finally:
        trans.rollback()
        conn.close()
        engine.dispose()
