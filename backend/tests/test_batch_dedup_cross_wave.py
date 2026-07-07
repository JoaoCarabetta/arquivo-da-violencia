"""Tests for Phase 1 matching inside batch dedup (cross-wave duplicate prevention)."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.models.raw_event import RawEvent
from app.models.unique_event import UniqueEvent
from app.services.enrichment import process_pending_deduplication


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _MatchedStub:
    def __init__(self, unique_event_id: int):
        self.id = unique_event_id


@pytest.mark.asyncio
async def test_batch_dedup_links_pending_raw_to_existing_unique_event(async_session):
    """Second-wave pending raw should match an existing UniqueEvent, not spawn a duplicate."""
    existing = UniqueEvent(
        title="HOMICÍDIO - VIA PÚBLICA SERTÃO DO MARUIM - 06/07/2026",
        event_date=datetime(2026, 7, 6),
        city="São José",
        state="SC",
        neighborhood="Sertão do Maruim",
        homicide_type="Feminicídio",
        victim_count=1,
        source_count=2,
        chronological_description="Mulher encontrada nua no canteiro central.",
    )
    async_session.add(existing)
    await async_session.commit()
    await async_session.refresh(existing)
    existing_id = existing.id

    pending = RawEvent(
        title="FEMINICÍDIO - RODOVIA SC-281, SERTÃO DO MARUIM - 06/07/2026",
        event_date=datetime(2026, 7, 6),
        city="São José",
        state="SC",
        neighborhood="Sertão do Maruim",
        homicide_type="Feminicídio",
        victim_count=1,
        source_google_news_id=1,
        deduplication_status="pending",
        chronological_description=(
            "Motorista de aplicativo encontrou mulher nua no canteiro da SC-281."
        ),
    )
    async_session.add(pending)
    await async_session.commit()
    await async_session.refresh(pending)
    pending_id = pending.id

    def fake_llm_match(raw_event, candidates, **kwargs):
        return _MatchedStub(existing_id), 0.95, "same incident"

    link_mock = AsyncMock()

    with (
        patch(
            "app.services.enrichment.async_session_maker",
            _TestSessionMaker(async_session),
        ),
        patch(
            "app.services.enrichment.llm_match_to_unique_event",
            side_effect=fake_llm_match,
        ),
        patch(
            "app.services.enrichment.link_raw_event_to_unique_event",
            link_mock,
        ),
        patch(
            "app.services.enrichment.create_unique_event_from_cluster",
        ) as mock_create,
    ):
        result = await process_pending_deduplication(limit=10)

    assert result["matched_to_existing"] == 1
    assert result["unique_events_created"] == 0
    mock_create.assert_not_called()
    link_mock.assert_awaited_once_with(pending_id, existing_id)


@pytest.mark.asyncio
async def test_batch_dedup_still_clusters_when_no_existing_match(async_session):
    """Pending raws with no existing UniqueEvent still cluster into one new event."""
    pending_a = RawEvent(
        title="HOMICÍDIO - BAIRRO CENTRO - 01/01/2026",
        event_date=datetime(2026, 1, 1),
        city="Testville",
        state="TS",
        source_google_news_id=1,
        deduplication_status="pending",
    )
    pending_b = RawEvent(
        title="HOMICÍDIO - CENTRO - 01/01/2026",
        event_date=datetime(2026, 1, 1),
        city="Testville",
        state="TS",
        source_google_news_id=2,
        deduplication_status="pending",
    )
    async_session.add_all([pending_a, pending_b])
    await async_session.commit()
    await async_session.refresh(pending_a)
    await async_session.refresh(pending_b)

    create_mock = AsyncMock(return_value=UniqueEvent(id=999, source_count=2))

    with (
        patch(
            "app.services.enrichment.async_session_maker",
            _TestSessionMaker(async_session),
        ),
        patch(
            "app.services.enrichment.llm_match_to_unique_event",
            return_value=(None, 0.0, "no match"),
        ),
        patch(
            "app.services.enrichment.llm_cluster_events",
            return_value=[[pending_a, pending_b]],
        ),
        patch(
            "app.services.enrichment.create_unique_event_from_cluster",
            create_mock,
        ),
    ):
        result = await process_pending_deduplication(limit=10)

    assert result["matched_to_existing"] == 0
    assert result["unique_events_created"] == 1
    create_mock.assert_awaited_once()
    cluster = create_mock.await_args.args[0]
    assert len(cluster) == 2
    assert {e.id for e in cluster} == {pending_a.id, pending_b.id}
