"""Issue #274: l1m2/m2n3 official_violence_count migrations must be idempotent by constraint name."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import StaticPool

backend_path = Path(__file__).parent.parent
alembic_versions_path = backend_path / "alembic" / "versions"
sys.path.insert(0, str(alembic_versions_path))

from l1m2n3o4p5q6_add_official_violence_count_table import (  # noqa: E402
    upgrade as l1_upgrade,
)

HEAD_REVISION = "n3o4p5q6r7s8"
PROD_LIKE_REVISION = "i8j9k0l1m2n3"
STAGING_ALEMBIC_REVISION = "k0l1m2n3o4p5"
FIVE_COL_UQ = {"code_muni", "year_month", "indicator", "source_id", "revision"}


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _postgres_engine_or_skip():
    candidates = []
    if os.environ.get("DATABASE_URL"):
        candidates.append(_normalize_postgres_url(os.environ["DATABASE_URL"]))
    candidates.extend(
        _normalize_postgres_url(f"postgresql://arquivo_dev:arquivo_dev@{host}:5432/arquivo_dev")
        for host in ("localhost", "postgres")
    )
    candidates.extend(
        _normalize_postgres_url(f"postgresql://arquivo:arquivo_dev@{host}:5432/arquivo_dev")
        for host in ("localhost", "postgres")
    )

    last_connect_error: Exception | None = None
    for db_url in candidates:
        try:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine, db_url
        except (ImportError, ModuleNotFoundError):
            raise
        except (OperationalError, DBAPIError) as exc:
            last_connect_error = exc
            continue
    pytest.skip(
        "Postgres not available for alembic upgrade head tests"
        + (f": {last_connect_error}" if last_connect_error else "")
    )


def _clear_settings_cache() -> None:
    from app.config import get_settings

    get_settings.cache_clear()


def _alembic_upgrade(database_url: str, revision: str = "head") -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=backend_path,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic upgrade {revision} failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _reset_postgres_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))


def _current_alembic_revision(engine) -> str | None:
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def _assert_five_column_uq_official_violence_key(engine) -> None:
    with engine.connect() as conn:
        inspector = inspect(conn)
        assert "official_violence_count" in inspector.get_table_names()
        constraints = inspector.get_unique_constraints("official_violence_count")
        uq = next(
            (c for c in constraints if c.get("name") == "uq_official_violence_key"),
            None,
        )
        if uq is None:
            uq = next(
                (c for c in constraints if set(c["column_names"]) == FIVE_COL_UQ),
                None,
            )
        if uq is None and engine.dialect.name == "sqlite":
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name = 'official_violence_count'")
            ).scalar()
            import re

            assert ddl and re.search(
                r"\bCONSTRAINT\s+uq_official_violence_key\b",
                ddl,
                re.IGNORECASE,
            ), f"DDL missing UQ: {ddl}"
            return
        assert uq is not None, f"uq_official_violence_key missing; constraints={constraints}"
        assert set(uq["column_names"]) == FIVE_COL_UQ


def _create_staging_official_violence_count_postgres(conn) -> None:
    """Table + 5-column uq as on staging before alembic caught up (issue #274)."""
    conn.execute(
        text(
            """
            CREATE TABLE official_violence_count (
                id SERIAL PRIMARY KEY,
                code_muni INTEGER NOT NULL,
                year_month VARCHAR(7) NOT NULL,
                indicator VARCHAR(50) NOT NULL,
                victim_count INTEGER NOT NULL,
                is_total BOOLEAN NOT NULL,
                source VARCHAR(100) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                source_id VARCHAR NOT NULL DEFAULT 'validador',
                revision VARCHAR NOT NULL DEFAULT 'consolidado',
                CONSTRAINT uq_official_violence_key UNIQUE (
                    code_muni, year_month, indicator, source_id, revision
                )
            )
            """
        )
    )
    for col in ("code_muni", "year_month", "indicator", "source_id", "revision"):
        conn.execute(
            text(
                f"CREATE INDEX ix_official_violence_count_{col} "
                f"ON official_violence_count ({col})"
            )
        )


def _create_staging_official_violence_count_sqlite(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE official_violence_count (
                id INTEGER PRIMARY KEY,
                code_muni INTEGER NOT NULL,
                year_month VARCHAR(7) NOT NULL,
                indicator VARCHAR(50) NOT NULL,
                victim_count INTEGER NOT NULL,
                is_total BOOLEAN NOT NULL,
                source VARCHAR(100) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                source_id VARCHAR NOT NULL DEFAULT 'validador',
                revision VARCHAR NOT NULL DEFAULT 'consolidado',
                CONSTRAINT uq_official_violence_key UNIQUE (
                    code_muni, year_month, indicator, source_id, revision
                )
            )
            """
        )
    )


@pytest.fixture
def sqlite_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_l1_upgrade_skips_uq_when_five_column_key_exists(sqlite_engine):
    """Staging shape on SQLite: l1 must not recreate uq_official_violence_key by name."""
    with sqlite_engine.begin() as connection:
        _create_staging_official_violence_count_sqlite(connection)

    with sqlite_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        import alembic.op as op_module

        op_module._proxy = ops
        l1_upgrade()  # must not raise on duplicate constraint name

    _assert_five_column_uq_official_violence_key(sqlite_engine)


@pytest.mark.parametrize(
    "start_revision, staging_table",
    [
        ("", False),
        (PROD_LIKE_REVISION, False),
        (STAGING_ALEMBIC_REVISION, True),
    ],
    ids=["fresh_empty_db", "prod_like_i8j9k0l1m2n3", "staging_k0l1_with_5col_uq"],
)
def test_alembic_upgrade_head_postgres(start_revision, staging_table):
    engine, sync_url = _postgres_engine_or_skip()
    async_url = sync_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

    _reset_postgres_schema(engine)
    _clear_settings_cache()

    if start_revision:
        _alembic_upgrade(async_url, start_revision)
        if staging_table:
            with engine.begin() as conn:
                _create_staging_official_violence_count_postgres(conn)
    else:
        assert _current_alembic_revision(engine) is None

    _alembic_upgrade(async_url, "head")

    assert _current_alembic_revision(engine) == HEAD_REVISION
    _assert_five_column_uq_official_violence_key(engine)


