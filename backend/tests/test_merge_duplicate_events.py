"""Tests for exact duplicate unique_event merge backfill (AQV-39)."""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.raw_event import RawEvent
from app.models.unique_event import UniqueEvent
from app.services.maintenance import (
    duplicate_group_key,
    merge_exact_duplicate_unique_events,
    normalize_city,
    pick_survivor_id,
)


def test_normalize_city_strips_accents():
    assert normalize_city("São Paulo") == "sao paulo"


def test_duplicate_group_key_requires_all_fields():
    dt = datetime(2025, 1, 15)
    assert duplicate_group_key("Homicídio", "Rio", dt) == (
        "homicidio",
        "rio",
        "2025-01-15",
    )
    assert duplicate_group_key(None, "Rio", dt) is None
    assert duplicate_group_key("Title", None, dt) is None
    assert duplicate_group_key("Title", "Rio", None) is None


def test_pick_survivor_prefers_higher_source_count():
    members = [
        {"id": 1, "source_count": 2},
        {"id": 2, "source_count": 5},
        {"id": 3, "source_count": 1},
    ]
    assert pick_survivor_id(members) == 2


def test_pick_survivor_tiebreaks_on_lowest_id():
    members = [
        {"id": 10, "source_count": 3},
        {"id": 5, "source_count": 3},
    ]
    assert pick_survivor_id(members) == 5


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_merge_dry_run_reports_groups(async_session):
    base = dict(
        title="Homicídio em Juiz de Fora",
        event_date=datetime(2025, 3, 1),
        city="Juiz de Fora",
        state="MG",
    )
    survivor = UniqueEvent(**base, source_count=3)
    loser = UniqueEvent(**base, source_count=1)
    async_session.add_all([survivor, loser])
    await async_session.commit()
    await async_session.refresh(survivor)
    await async_session.refresh(loser)
    survivor_id = survivor.id
    loser_id = loser.id

    async_session.add(
        RawEvent(
            title=base["title"],
            event_date=base["event_date"],
            city=base["city"],
            state=base["state"],
            source_google_news_id=1,
            unique_event_id=loser_id,
            deduplication_status="matched",
        )
    )
    await async_session.commit()

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await merge_exact_duplicate_unique_events(dry_run=True)

    assert audit["groups_found"] == 1
    assert audit["events_merged"] == 1
    assert audit["raw_events_relinked"] == 1
    assert audit["merges"][0]["survivor_id"] == survivor_id
    assert audit["merges"][0]["loser_ids"] == [loser_id]

    count = await async_session.execute(text("SELECT COUNT(*) FROM unique_event"))
    assert count.scalar_one() == 2


@pytest.mark.asyncio
async def test_merge_execute_relinks_and_deletes_loser(async_session):
    base = dict(
        title="Tiroteio na Zona Norte",
        event_date=datetime(2025, 6, 10),
        city="Rio de Janeiro",
        state="RJ",
    )
    survivor = UniqueEvent(**base, source_count=2)
    loser = UniqueEvent(**base, source_count=1)
    async_session.add_all([survivor, loser])
    await async_session.commit()
    await async_session.refresh(survivor)
    await async_session.refresh(loser)
    survivor_id = survivor.id
    loser_id = loser.id

    raw_on_loser = RawEvent(
        title=base["title"],
        event_date=base["event_date"],
        city=base["city"],
        state=base["state"],
        source_google_news_id=1,
        unique_event_id=loser_id,
        deduplication_status="matched",
    )
    raw_on_survivor = RawEvent(
        title=base["title"],
        event_date=base["event_date"],
        city=base["city"],
        state=base["state"],
        source_google_news_id=2,
        unique_event_id=survivor_id,
        deduplication_status="matched",
    )
    async_session.add_all([raw_on_loser, raw_on_survivor])
    await async_session.commit()

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await merge_exact_duplicate_unique_events(dry_run=False)

    assert audit["events_merged"] == 1

    remaining = await async_session.execute(text("SELECT COUNT(*) FROM unique_event"))
    assert remaining.scalar_one() == 1

    raw_count = await async_session.execute(
        text("""
            SELECT COUNT(*) FROM raw_event WHERE unique_event_id = :id
        """),
        {"id": survivor_id},
    )
    assert raw_count.scalar_one() == 2

    source_count = await async_session.execute(
        text("SELECT source_count, needs_enrichment FROM unique_event WHERE id = :id"),
        {"id": survivor_id},
    )
    row = source_count.one()
    assert row.source_count == 2
    assert row.needs_enrichment == 1


@pytest.mark.asyncio
async def test_merge_copies_geocoding_when_survivor_lacks_coords(async_session):
    base = dict(
        title="Assassinato no Centro",
        event_date=datetime(2025, 2, 20),
        city="Belo Horizonte",
        state="MG",
    )
    survivor = UniqueEvent(**base, source_count=4)
    loser = UniqueEvent(
        **base,
        source_count=1,
        latitude="-19.91668130",
        longitude="-43.93449310",
        place_id="ChIJplace",
        formatted_address="Centro, Belo Horizonte",
        geocoding_source="google_maps",
    )
    async_session.add_all([survivor, loser])
    await async_session.commit()
    await async_session.refresh(survivor)
    await async_session.refresh(loser)

    survivor_id = survivor.id

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        await merge_exact_duplicate_unique_events(dry_run=False)

    result = await async_session.execute(
        text("""
            SELECT latitude, longitude, place_id, formatted_address
            FROM unique_event WHERE id = :id
        """),
        {"id": survivor_id},
    )
    row = result.one()
    assert row.latitude is not None
    assert row.place_id == "ChIJplace"
    assert row.formatted_address == "Centro, Belo Horizonte"
