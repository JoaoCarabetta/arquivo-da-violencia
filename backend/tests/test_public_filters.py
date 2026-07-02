"""Tests for public incident guardrail filters (AQV-29 Phase A)."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import select, func

from app.models.unique_event import UniqueEvent
from app.services.public_filters import BR_UFS, apply_public_incident_filter


def _make_event(**kwargs) -> UniqueEvent:
    defaults = {
        "title": "Test event",
        "event_date": datetime.utcnow() - timedelta(days=1),
        "state": "RJ",
        "city": "Rio de Janeiro",
        "victim_count": 1,
        "latitude": Decimal("-22.9068"),
        "longitude": Decimal("-43.1729"),
    }
    defaults.update(kwargs)
    return UniqueEvent(**defaults)


@pytest.mark.asyncio
async def test_filter_excludes_high_victim_count(async_session):
    valid = _make_event(title="Valid", victim_count=10)
    inflated = _make_event(title="Inflated", victim_count=11)
    async_session.add(valid)
    async_session.add(inflated)
    await async_session.commit()

    query = apply_public_incident_filter(select(func.count(UniqueEvent.id)))
    result = await async_session.exec(query)
    assert result.one() == 1


@pytest.mark.asyncio
async def test_filter_excludes_foreign_state(async_session):
    br_event = _make_event(title="Brazil", state="SP")
    foreign = _make_event(title="Foreign", state="US")
    async_session.add(br_event)
    async_session.add(foreign)
    await async_session.commit()

    query = apply_public_incident_filter(select(func.count(UniqueEvent.id)))
    result = await async_session.exec(query)
    assert result.one() == 1


@pytest.mark.asyncio
async def test_filter_includes_null_state(async_session):
    event = _make_event(title="Unknown state", state=None)
    async_session.add(event)
    await async_session.commit()

    query = apply_public_incident_filter(select(func.count(UniqueEvent.id)))
    result = await async_session.exec(query)
    assert result.one() == 1


@pytest.mark.asyncio
async def test_filter_excludes_null_victim_count(async_session):
    event = _make_event(title="No count", victim_count=None)
    async_session.add(event)
    await async_session.commit()

    query = apply_public_incident_filter(select(func.count(UniqueEvent.id)))
    result = await async_session.exec(query)
    assert result.one() == 0


@pytest.mark.asyncio
async def test_public_stats_excludes_inflated_rows(client: AsyncClient, async_session):
    async_session.add(_make_event(title="Valid"))
    async_session.add(_make_event(title="Inflated", victim_count=100))
    async_session.add(_make_event(title="Foreign", state="MX"))
    await async_session.commit()

    response = await client.get("/api/public/stats")
    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.asyncio
async def test_map_points_excludes_inflated_rows(client: AsyncClient, async_session):
    async_session.add(_make_event(title="Valid"))
    async_session.add(_make_event(title="Inflated", victim_count=50))
    await async_session.commit()

    response = await client.get("/api/public/map-points?days=365")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_unique_events_stats_summary_excludes_inflated(async_session, app):
    from app.database import get_session

    async_session.add(_make_event(title="Valid", victim_count=2))
    async_session.add(_make_event(title="Inflated", victim_count=20))
    await async_session.commit()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=__import__("httpx").ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/unique-events/stats/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["total_victims"] == 2


def test_br_ufs_has_27_states():
    assert len(BR_UFS) == 27
