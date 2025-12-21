"""Database configuration and session management."""

from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings


def _normalize_database_url(db_url: str) -> str:
    """Normalize database URL to ensure async driver is used."""
    # Ensure aiosqlite driver is used for SQLite
    if db_url.startswith("sqlite:///"):
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    
    # Handle relative paths for SQLite
    if db_url.startswith("sqlite+aiosqlite:///"):
        path_part = db_url.split("sqlite+aiosqlite:///")[-1]
        if path_part and not path_part.startswith("/"):
            # Relative path - convert to absolute
            abs_path = (Path.cwd() / path_part).resolve()
            # Ensure parent directory exists
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite+aiosqlite:///{abs_path}"
    
    return db_url


@lru_cache
def get_engine() -> AsyncEngine:
    """Get cached async engine instance."""
    settings = get_settings()
    db_url = _normalize_database_url(settings.database_url)
    
    return create_async_engine(
        db_url,
        echo=settings.debug,
        future=True,
    )


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
