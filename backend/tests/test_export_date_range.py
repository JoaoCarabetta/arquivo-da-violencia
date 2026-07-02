"""Tests for CSV export date range filtering."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.models.unique_event import UniqueEvent


@pytest.fixture(autouse=True)
def bypass_export_rate_limit():
    with patch(
        "app.services.geocode_protection.enforce_export_rate_limit",
        AsyncMock(return_value=None),
    ):
        yield


@pytest.mark.asyncio
async def test_export_filters_by_date_range(app, async_session, client: AsyncClient):
    inside = UniqueEvent(
        title="Inside range",
        event_date=datetime(2024, 6, 15, 12, 0, 0),
        state="RJ",
        city="Rio de Janeiro",
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
    )
    outside = UniqueEvent(
        title="Outside range",
        event_date=datetime(2024, 1, 1, 12, 0, 0),
        state="SP",
        city="São Paulo",
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
    )
    async_session.add(inside)
    async_session.add(outside)
    await async_session.commit()

    response = await client.get(
        "/api/public/events/export",
        params={"start_date": "2024-06-01", "end_date": "2024-06-30"},
    )
    assert response.status_code == 200
    assert "Inside range" in response.text
    assert "Outside range" not in response.text


@pytest.mark.asyncio
async def test_export_rejects_invalid_date_range(client: AsyncClient):
    response = await client.get(
        "/api/public/events/export",
        params={"start_date": "2024-06-30", "end_date": "2024-06-01"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_export_without_date_range_uses_days_window(app, async_session, client: AsyncClient):
    recent = UniqueEvent(
        title="Recent event",
        event_date=datetime.utcnow() - timedelta(days=10),
        state="RJ",
        city="Niterói",
        latitude=Decimal("-22.8832"),
        longitude=Decimal("-43.1034"),
    )
    old = UniqueEvent(
        title="Old event",
        event_date=datetime.utcnow() - timedelta(days=400),
        state="RJ",
        city="Volta Redonda",
        latitude=Decimal("-22.5202"),
        longitude=Decimal("-44.0996"),
    )
    async_session.add(recent)
    async_session.add(old)
    await async_session.commit()

    response = await client.get("/api/public/events/export", params={"days": 365})
    assert response.status_code == 200
    assert "Recent event" in response.text
    assert "Old event" not in response.text
