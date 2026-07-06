"""Alembic migration environment configuration."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context

# Import all models so they are registered with SQLModel.metadata
from app.models import (  # noqa: F401
    SourceGoogleNews,
    RawEvent,
    UniqueEvent,
)
from app.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _migration_database_url() -> str:
    """Return a sync SQLAlchemy URL suitable for Alembic migrations."""
    db_url = get_settings().database_url
    if "+aiosqlite" in db_url:
        return db_url.replace("+aiosqlite", "")
    if "+asyncpg" in db_url:
        return db_url.replace("+asyncpg", "+psycopg")
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if db_url.startswith("postgres://"):
        return db_url.replace("postgres://", "postgresql+psycopg://", 1)
    return db_url


config.set_main_option("sqlalchemy.url", _migration_database_url())


def _configure_context(connection=None, *, url: str | None = None) -> None:
    dialect_name = connection.dialect.name if connection is not None else None
    if dialect_name is None and url:
        if "sqlite" in url:
            dialect_name = "sqlite"
        elif "postgresql" in url:
            dialect_name = "postgresql"

    kwargs = {
        "target_metadata": target_metadata,
        "render_as_batch": dialect_name == "sqlite",
    }
    if connection is not None:
        kwargs["connection"] = connection
    else:
        kwargs["url"] = url
        kwargs["literal_binds"] = True
        kwargs["dialect_opts"] = {"paramstyle": "named"}

    context.configure(**kwargs)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    _configure_context(url=url)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _configure_context(connection=connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
