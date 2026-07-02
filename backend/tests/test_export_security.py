"""Tests for CSV export security hardening (columns, caps, rate limits)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.unique_event import UniqueEvent
from app.routers import public as public_router
from tests.test_geocode_protection import FakeRedis


@pytest.mark.asyncio
async def test_export_default_excludes_internal_columns(app, async_session, client: AsyncClient):
    event = UniqueEvent(
        title="Public event",
        event_date=datetime.utcnow(),
        state="RJ",
        city="Rio de Janeiro",
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
        place_id="secret-place-id",
        merged_data={"internal": True},
        confirmed=True,
        needs_enrichment=True,
        enrichment_model="gemini",
    )
    async_session.add(event)
    await async_session.commit()

    with patch(
        "app.services.geocode_protection.enforce_export_rate_limit",
        AsyncMock(return_value=None),
    ):
        response = await client.get("/api/public/events/export")

    assert response.status_code == 200
    header = response.text.splitlines()[0]
    assert "merged_data" not in header
    assert "place_id" not in header
    assert "confirmed" not in header
    assert "needs_enrichment" not in header
    assert "enrichment_model" not in header
    assert "title" in header


@pytest.mark.asyncio
async def test_export_rejects_internal_column_requests(client: AsyncClient):
    with patch(
        "app.services.geocode_protection.enforce_export_rate_limit",
        AsyncMock(return_value=None),
    ):
        response = await client.get(
            "/api/public/events/export",
            params={"columns": ["merged_data", "place_id"]},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_export_json_sets_truncated_header(app, async_session, client: AsyncClient):
    for index in range(3):
        async_session.add(
            UniqueEvent(
                title=f"Event {index}",
                event_date=datetime.utcnow(),
                state="RJ",
                city="Niterói",
                latitude=Decimal("-22.8832"),
                longitude=Decimal("-43.1034"),
            )
        )
    await async_session.commit()

    with (
        patch.object(public_router, "EXPORT_MAX_ROWS", 2),
        patch(
            "app.services.geocode_protection.enforce_export_rate_limit",
            AsyncMock(return_value=None),
        ),
    ):
        response = await client.get("/api/public/events/export", params={"format": "json"})

    assert response.status_code == 200
    assert response.headers.get("X-Export-Truncated") == "true"
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_export_rate_limit_returns_429(client: AsyncClient):
    redis_stub = FakeRedis()

    with patch(
        "app.services.geocode_protection._get_redis",
        AsyncMock(return_value=redis_stub),
    ):
        for _ in range(5):
            ok = await client.get("/api/public/events/export")
            assert ok.status_code == 200
        blocked = await client.get("/api/public/events/export")

    assert blocked.status_code == 429
