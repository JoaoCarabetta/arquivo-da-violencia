"""Tests for streaming CSV export (row completeness)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.unique_event import UniqueEvent


@pytest.mark.asyncio
async def test_export_csv_returns_all_geocoded_rows(app, async_session, client: AsyncClient):
    """Streaming CSV path should include every matching row, not truncate early."""
    for index in range(5):
        async_session.add(
            UniqueEvent(
                title=f"Export event {index}",
                event_date=datetime(2026, 1, index + 1),
                state="RJ",
                city="Rio de Janeiro",
                latitude=Decimal("-22.9068"),
                longitude=Decimal("-43.1729"),
            )
        )
    await async_session.commit()

    with patch(
        "app.services.geocode_protection.enforce_export_rate_limit",
        AsyncMock(return_value=None),
    ):
        response = await client.get("/api/public/events/export", params={"days": 3650})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    lines = [line for line in response.text.splitlines() if line.strip()]
    assert len(lines) == 6  # header + 5 data rows
