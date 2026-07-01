"""Tests for pipeline route authentication."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.main import create_app


@pytest.fixture
def auth_enabled(monkeypatch):
    """Enable JWT auth for the duration of the test."""
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("ADMIN_USERNAME", "testadmin")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")


@pytest.fixture
async def auth_client(auth_enabled):
    """Test client with auth enabled."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


def _auth_header(username: str = "testadmin") -> dict[str, str]:
    token = create_access_token({"sub": username})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_pipeline_status_requires_auth(auth_client):
    response = await auth_client.get("/api/pipeline/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pipeline_full_requires_auth(auth_client):
    response = await auth_client.post("/api/pipeline/full")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pipeline_status_with_valid_token(auth_client):
    response = await auth_client.get(
        "/api/pipeline/status",
        headers=_auth_header(),
    )
    # Auth passes; Redis may be unavailable in CI (503) or connected (200).
    assert response.status_code in (200, 503)


@pytest.mark.asyncio
async def test_pipeline_telegram_test_requires_auth(auth_client):
    response = await auth_client.post("/api/pipeline/telegram/test")
    assert response.status_code == 401
