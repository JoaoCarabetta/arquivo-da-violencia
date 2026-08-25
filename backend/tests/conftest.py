"""Pytest fixtures for testing."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.main import create_app
from app.database import get_session


@pytest.fixture(autouse=True)
def use_test_mode_for_municipality_polygons():
    """
    Enable test fixture mode for all tests (issue #179).
    
    Ensures unit tests use the small bundled fixture (Rio, Brasília, São Paulo)
    and NEVER call the live geobr API to download municipality polygons.
    """
    from app.services.municipality_codes import set_test_mode
    set_test_mode(True)
    yield
    set_test_mode(False)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for pytest-asyncio."""
    return "asyncio"


@pytest.fixture
async def async_engine():
    """Create an in-memory async engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    """Create an async session for testing."""
    async with AsyncSession(async_engine) as session:
        yield session


@pytest.fixture
async def app(async_session):
    """Create test application with overridden dependencies."""
    app = create_app()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def population_fixture(async_session):
    """Load IBGE population fixture data for testing."""
    from app.services.ibge_population import load_ibge_population_fixture
    await load_ibge_population_fixture(async_session)
    yield

