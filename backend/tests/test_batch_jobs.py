"""Tests for pipeline batch job helpers."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.batch_jobs import (
    ALL_DRAIN_STAGES,
    _date_clause,
    _ids_clause,
    _location_clause,
    _parse_ids,
    clear_geocode_for_requeue,
    dedup_keys_changed,
    enqueue_drain,
    flag_unique_needs_enrichment,
    reextract_sources,
    update_raw_event_in_place,
)
from app.services.extraction import raw_event_fields_from_event
from app.services.extraction_schemas import (
    DateTime,
    DateVerification,
    HomicideDynamic,
    Location,
    Victims,
    ViolentDeathEvent,
)


def _minimal_event(
    *,
    content_class: str = "incident",
    title: str = "Homem é morto a tiros",
    event_date: str | None = "2026-03-15",
) -> ViolentDeathEvent:
    return ViolentDeathEvent(
        event_family="homicidio",
        event_subtype="simples",
        content_class=content_class,  # type: ignore[arg-type]
        location_info=Location(city="São Paulo", state="SP", neighborhood="Centro"),
        date_time=DateTime(
            date_verification=DateVerification(
                has_explicit_date=bool(event_date),
                date_source="explicit" if event_date else "none",
                year_explicitly_mentioned=bool(event_date),
                verification_reasoning="test",
            ),
            date=event_date,
            date_precision="exata" if event_date else "não informada",
        ),
        victims=Victims(
            identifiable_victims=[],
            number_of_identifiable_victims=0,
            number_of_victims=1,
        ),
        homicide_dynamic=HomicideDynamic(
            title=title,
            chronological_description="Vítima foi alvejada.",
            method="Arma de fogo",
        ),
    )


def test_parse_ids_empty():
    assert _parse_ids(None) == []
    assert _parse_ids([]) == []


def test_parse_ids_values():
    assert _parse_ids([1, "2", 3]) == [1, 2, 3]


def test_date_clause_since_until():
    params: dict = {}
    clause = _date_clause(
        "event_date", since=date(2026, 1, 1), until=date(2026, 6, 30), params=params
    )
    assert "CAST(event_date AS DATE) >= :since" in clause
    assert "CAST(event_date AS DATE) <= :until" in clause
    assert params["since"] == date(2026, 1, 1)
    assert params["until"] == date(2026, 6, 30)


def test_location_clause():
    params: dict = {}
    clause = _location_clause(city="Rio de Janeiro", state="RJ", params=params)
    assert "LOWER(city) = :city" in clause
    assert params["city"] == "rio de janeiro"
    assert params["state"] == "rj"


def test_ids_clause():
    params: dict = {}
    clause = _ids_clause("id", [10, 20], params)
    assert "id IN (:id_0, :id_1)" in clause
    assert params["id_0"] == 10
    assert params["id_1"] == 20


def test_dedup_keys_changed_detects_city_and_date():
    candidate = {
        "city": "São Paulo",
        "state": "SP",
        "event_date": datetime(2026, 3, 15),
    }
    assert not dedup_keys_changed(
        candidate,
        {"city": "São Paulo", "state": "SP", "event_date": datetime(2026, 3, 15)},
    )
    assert dedup_keys_changed(
        candidate,
        {"city": "Campinas", "state": "SP", "event_date": datetime(2026, 3, 15)},
    )
    assert dedup_keys_changed(
        candidate,
        {"city": "São Paulo", "state": "SP", "event_date": datetime(2026, 3, 16)},
    )


def test_raw_event_fields_from_event_maps_core_columns():
    fields = raw_event_fields_from_event(_minimal_event())
    assert fields["city"] == "São Paulo"
    assert fields["state"] == "SP"
    assert fields["content_class"] == "incident"
    assert fields["extraction_success"] is True
    assert fields["event_date"] == datetime(2026, 3, 15)
    assert fields["extraction_data"]["homicide_dynamic"]["title"] == "Homem é morto a tiros"


@pytest.mark.asyncio
async def test_reextract_dry_run_does_not_call_llm():
    candidates = [
        {
            "source_id": 1,
            "raw_event_id": 10,
            "unique_event_id": 100,
            "city": "SP",
            "event_date": datetime(2026, 1, 2),
            "headline": "Test",
        }
    ]
    with patch(
        "app.services.batch_jobs.find_reextract_candidates",
        new=AsyncMock(return_value=candidates),
    ), patch(
        "app.services.extraction.extract_event_from_content",
    ) as extract_mock:
        audit = await reextract_sources(dry_run=True, limit=5)
        extract_mock.assert_not_called()
    assert audit["candidate_count"] == 1
    assert audit["updated"] == 0
    assert audit["samples"][0]["source_id"] == 1


@pytest.mark.asyncio
async def test_reextract_execute_updates_in_place_and_flags_enrichment():
    candidates = [
        {
            "source_id": 1,
            "raw_event_id": 10,
            "unique_event_id": 100,
            "city": "São Paulo",
            "state": "SP",
            "event_date": datetime(2026, 1, 2),
            "headline": "Test",
        }
    ]
    event = _minimal_event(title="Updated title", event_date="2026-01-02")
    source_row = ("body " * 50, "headline", datetime(2026, 1, 3), "Publisher", "http://x")

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    execute_result = MagicMock()
    execute_result.fetchone.return_value = source_row
    session.execute = AsyncMock(return_value=execute_result)

    with patch(
        "app.services.batch_jobs.find_reextract_candidates",
        new=AsyncMock(return_value=candidates),
    ), patch(
        "app.services.batch_jobs.async_session_maker",
        return_value=session,
    ), patch(
        "app.services.extraction.extract_event_from_content",
        return_value=event,
    ), patch(
        "app.services.batch_jobs.update_raw_event_in_place",
        new=AsyncMock(),
    ) as update_mock, patch(
        "app.services.batch_jobs.flag_unique_needs_enrichment",
        new=AsyncMock(return_value=1),
    ) as flag_mock:
        audit = await reextract_sources(dry_run=False, limit=5, concurrency=1)

    assert audit["updated"] == 1
    assert audit["failed"] == 0
    assert audit["would_discard"] == 0
    update_mock.assert_awaited_once()
    assert update_mock.await_args.args[0] == 10
    assert update_mock.await_args.kwargs.get("unlink_for_rededup") is False
    flag_mock.assert_awaited_once()
    assert 100 in list(flag_mock.await_args.args[0])


@pytest.mark.asyncio
async def test_reextract_unlinks_when_city_changes():
    candidates = [
        {
            "source_id": 1,
            "raw_event_id": 10,
            "unique_event_id": 100,
            "city": "Rio de Janeiro",
            "state": "RJ",
            "event_date": datetime(2026, 1, 2),
            "headline": "Test",
        }
    ]
    event = _minimal_event(title="Updated title", event_date="2026-01-02")
    source_row = ("body " * 50, "headline", datetime(2026, 1, 3), "Publisher", "http://x")
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    execute_result = MagicMock()
    execute_result.fetchone.return_value = source_row
    session.execute = AsyncMock(return_value=execute_result)

    with patch(
        "app.services.batch_jobs.find_reextract_candidates",
        new=AsyncMock(return_value=candidates),
    ), patch(
        "app.services.batch_jobs.async_session_maker",
        return_value=session,
    ), patch(
        "app.services.extraction.extract_event_from_content",
        return_value=event,
    ), patch(
        "app.services.batch_jobs.update_raw_event_in_place",
        new=AsyncMock(),
    ) as update_mock, patch(
        "app.services.batch_jobs.refresh_unique_source_counts",
        new=AsyncMock(return_value=1),
    ) as refresh_mock, patch(
        "app.services.batch_jobs.flag_unique_needs_enrichment",
        new=AsyncMock(return_value=0),
    ) as flag_mock:
        audit = await reextract_sources(dry_run=False, limit=5, concurrency=1)

    assert audit["updated"] == 1
    assert audit["unlinked_for_rededup"] == 1
    assert update_mock.await_args.kwargs.get("unlink_for_rededup") is True
    refresh_mock.assert_awaited_once()
    assert 100 in list(refresh_mock.await_args.args[0])
    flag_mock.assert_awaited_once()
    assert list(flag_mock.await_args.args[0]) == []


@pytest.mark.asyncio
async def test_reextract_would_discard_keeps_history():
    candidates = [
        {
            "source_id": 1,
            "raw_event_id": 10,
            "unique_event_id": 100,
            "city": "SP",
            "event_date": datetime(2026, 1, 2),
            "headline": "Test",
        }
    ]
    event = _minimal_event(content_class="aggregate_statistics", title="Stats")
    source_row = ("body " * 50, "headline", None, "Publisher", "http://x")
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    execute_result = MagicMock()
    execute_result.fetchone.return_value = source_row
    session.execute = AsyncMock(return_value=execute_result)

    with patch(
        "app.services.batch_jobs.find_reextract_candidates",
        new=AsyncMock(return_value=candidates),
    ), patch(
        "app.services.batch_jobs.async_session_maker",
        return_value=session,
    ), patch(
        "app.services.extraction.extract_event_from_content",
        return_value=event,
    ), patch(
        "app.services.batch_jobs.update_raw_event_in_place",
        new=AsyncMock(),
    ) as update_mock:
        audit = await reextract_sources(dry_run=False, limit=5, concurrency=1)

    assert audit["would_discard"] == 1
    assert audit["updated"] == 0
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_drain_uses_namespaced_pool():
    redis = AsyncMock()
    redis.enqueue_job = AsyncMock()
    redis.close = AsyncMock()

    with patch(
        "app.tasks.worker.create_arq_pool",
        new=AsyncMock(return_value=redis),
    ), patch(
        "app.tasks.worker.get_arq_queue_name",
        return_value="arquivo:test",
    ):
        result = await enqueue_drain(stages=["enrich", "geocode"])

    assert result["queue"] == "arquivo:test"
    assert result["enqueued"] == ["enrich:50", "geocode:200"]
    assert redis.enqueue_job.await_count == 2


@pytest.mark.asyncio
async def test_enqueue_drain_rejects_unknown_stage():
    with pytest.raises(ValueError, match="Unknown drain stages"):
        await enqueue_drain(stages=["nope"])


def test_all_drain_stages_complete():
    assert set(ALL_DRAIN_STAGES) == {
        "classify",
        "download",
        "extract",
        "dedup",
        "enrich",
        "geocode",
    }


@pytest.mark.asyncio
async def test_flag_unique_needs_enrichment_noop_on_empty():
    assert await flag_unique_needs_enrichment([]) == 0


@pytest.mark.asyncio
async def test_clear_geocode_noop_on_empty():
    assert await clear_geocode_for_requeue([]) == 0


@pytest.mark.asyncio
async def test_update_raw_event_in_place_sets_fields():
    raw = MagicMock()
    raw.id = 10
    result = MagicMock()
    result.scalar_one_or_none.return_value = raw

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    with patch("app.services.batch_jobs.async_session_maker", return_value=session):
        await update_raw_event_in_place(
            10,
            {"title": "New", "city": "Campinas", "extraction_data": {"a": 1}},
        )

    assert raw.title == "New"
    assert raw.city == "Campinas"
    session.commit.assert_awaited_once()
