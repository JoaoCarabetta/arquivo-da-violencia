"""Tests for CSV export column selection."""

from datetime import datetime
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
async def test_export_filters_columns(app, async_session, client: AsyncClient):
    event = UniqueEvent(
        title="Test event",
        event_date=datetime.utcnow(),
        state="RJ",
        city="Rio de Janeiro",
        homicide_type="Homicídio",
        method_of_death="Tiro",
        victim_count=1,
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
        source_count=1,
    )
    async_session.add(event)
    await async_session.commit()

    response = await client.get(
        "/api/public/events/export",
        params={"columns": ["id", "title", "city"]},
    )
    assert response.status_code == 200

    lines = response.text.strip().splitlines()
    assert lines[0] == "id,title,city"
    assert len(lines) == 2
    assert "Rio de Janeiro" in lines[1]


@pytest.mark.asyncio
async def test_export_rejects_invalid_columns(client: AsyncClient):
    response = await client.get(
        "/api/public/events/export",
        params={"columns": ["not_a_real_column"]},
    )
    assert response.status_code == 400
