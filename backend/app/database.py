"""Database configuration and session management."""

from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings


def _normalize_database_url(db_url: str) -> str:
    """Normalize database URL to ensure the correct async driver is used."""
    if db_url.startswith("sqlite:///"):
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

    if db_url.startswith("sqlite+aiosqlite:///"):
        path_part = db_url.split("sqlite+aiosqlite:///")[-1]
        if path_part and not path_part.startswith("/"):
            abs_path = (Path.cwd() / path_part).resolve()
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite+aiosqlite:///{abs_path}"

    return db_url


def sql_hour_bucket(column: str) -> str:
    """SQL expression that buckets a timestamp column to the start of its hour."""
    settings = get_settings()
    if settings.is_sqlite:
        return f"strftime('%Y-%m-%d %H:00:00', {column})"
    return (
        f"to_char(date_trunc('hour', {column} AT TIME ZONE 'UTC'), "
        f"'YYYY-MM-DD HH24:00:00')"
    )


def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Set SQLite pragmas for better concurrency and performance."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=60000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()


@lru_cache
def get_engine() -> AsyncEngine:
    """Get cached async engine instance."""
    settings = get_settings()
    db_url = _normalize_database_url(settings.database_url)

    common_kwargs = {
        "echo": settings.debug,
        "future": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_pool_overflow,
        "pool_timeout": 60,
        "pool_recycle": 1800,
    }

    if "sqlite" in db_url:
        engine = create_async_engine(
            db_url,
            connect_args={
                "check_same_thread": False,
                "timeout": 60,
            },
            **common_kwargs,
        )
        event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
        return engine

    return create_async_engine(db_url, **common_kwargs)


async def init_db() -> None:
    """Initialize database tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session."""
    engine = get_engine()
    async with AsyncSession(engine) as session:
        yield session


class AsyncSessionMaker:
    """Context manager for creating async sessions outside of FastAPI dependencies."""

    async def __aenter__(self) -> AsyncSession:
        self.session = AsyncSession(get_engine())
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()


def async_session_maker() -> AsyncSessionMaker:
    """Create a context manager for async sessions."""
    return AsyncSessionMaker()
