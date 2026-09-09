"""Tests for Brazil future-vs-publish event_date remediator (issue #228)."""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.models.unique_event import UniqueEvent
from app.services.extraction_heuristics import clamp_event_date_against_publish
from app.services.maintenance import remediate_future_event_dates


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def _seed_event(
    session,
    *,
    title: str,
    city: str,
    state: str,
    country: str,
    event_date: datetime,
    published_at: datetime | None,
    google_news_id: str,
    merged_date: str | None = None,
):
    unique = UniqueEvent(
        title=title,
        event_date=event_date,
        date_precision="exata",
        city=city,
        state=state,
        country=country,
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        source_count=1,
        merged_data={
            "date_time": {
                "date": merged_date or event_date.strftime("%Y-%m-%d"),
                "date_precision": "exata",
            }
        },
        created_at=datetime(2026, 8, 20, 18, 0, 0),
    )
    session.add(unique)
    await session.commit()
    await session.refresh(unique)
    unique_id = unique.id

    source = SourceGoogleNews(
        google_news_id=google_news_id,
        google_news_url=f"https://news.google.com/rss/articles/{google_news_id}",
        headline=title,
        content=f"Crime em {city}.",
        published_at=published_at,
        status=SourceStatus.extracted,
        country=country,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    source_id = source.id

    raw = RawEvent(
        title=title,
        event_date=event_date,
        date_precision="exata",
        city=city,
        state=state,
        country=country,
        source_google_news_id=source_id,
        unique_event_id=unique_id,
        deduplication_status="matched",
        extraction_data={
            "date_time": {
                "date": merged_date or event_date.strftime("%Y-%m-%d"),
                "date_precision": "exata",
            }
        },
    )
    session.add(raw)
    await session.commit()
    await session.refresh(raw)
    return unique, raw, source


@pytest.mark.asyncio
async def test_remediator_lins_shifts_to_previous_year(async_session):
    unique, raw, _source = await _seed_event(
        async_session,
        title="Homicídio em Lins",
        city="Lins",
        state="SP",
        country="BR",
        event_date=datetime(2026, 10, 16),
        published_at=datetime(2026, 8, 20, 12, 0, 0),
        google_news_id="lins-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_future_event_dates(dry_run=False)

    await async_session.refresh(unique)
    await async_session.refresh(raw)

    assert unique.event_date.date().isoformat() == "2025-10-16"
    assert unique.date_precision == "exata"
    assert unique.merged_data["date_time"]["date"] == "2025-10-16"
    assert raw.event_date.date().isoformat() == "2025-10-16"
    assert audit["updated"] == 1
    assert audit["dry_run"] is False


@pytest.mark.asyncio
async def test_remediator_bh_shifts_to_previous_year(async_session):
    unique, raw, _source = await _seed_event(
        async_session,
        title="Homicídio em Belo Horizonte",
        city="Belo Horizonte",
        state="MG",
        country="BR",
        event_date=datetime(2026, 10, 12),
        published_at=datetime(2026, 8, 20, 15, 0, 0),
        google_news_id="bh-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_future_event_dates()

    await async_session.refresh(unique)
    await async_session.refresh(raw)
    assert unique.event_date.date().isoformat() == "2025-10-12"
    assert raw.event_date.date().isoformat() == "2025-10-12"
    assert audit["updated"] == 1


@pytest.mark.asyncio
async def test_remediator_dry_run_does_not_write(async_session):
    unique, _raw, _source = await _seed_event(
        async_session,
        title="Homicídio em Lins",
        city="Lins",
        state="SP",
        country="BR",
        event_date=datetime(2026, 10, 16),
        published_at=datetime(2026, 8, 20, 12, 0, 0),
        google_news_id="lins-dry-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_future_event_dates(dry_run=True)

    await async_session.refresh(unique)
    assert unique.event_date.date().isoformat() == "2026-10-16"
    assert audit["dry_run"] is True
    assert audit["would_update"] == 1
    assert audit["updated"] == 0


@pytest.mark.asyncio
async def test_remediator_skips_non_brazil(async_session):
    unique, _raw, _source = await _seed_event(
        async_session,
        title="Homicidio en Santiago",
        city="Santiago",
        state="RM",
        country="CL",
        event_date=datetime(2026, 10, 16),
        published_at=datetime(2026, 8, 20, 12, 0, 0),
        google_news_id="cl-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_future_event_dates(dry_run=False)

    await async_session.refresh(unique)
    assert unique.event_date.date().isoformat() == "2026-10-16"
    assert audit["updated"] == 0


@pytest.mark.asyncio
async def test_remediator_falls_back_to_created_at_when_publish_missing(async_session):
    unique, raw, _source = await _seed_event(
        async_session,
        title="Homicídio em Lins",
        city="Lins",
        state="SP",
        country="BR",
        event_date=datetime(2026, 10, 16),
        published_at=None,
        google_news_id="lins-nopub-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        await remediate_future_event_dates(dry_run=False)

    await async_session.refresh(unique)
    await async_session.refresh(raw)
    assert unique.event_date.date().isoformat() == "2025-10-16"
    assert raw.event_date.date().isoformat() == "2025-10-16"


@pytest.mark.asyncio
async def test_remediator_nulls_when_previous_year_still_after_publish(async_session):
    unique, raw, _source = await _seed_event(
        async_session,
        title="Homicídio futuro",
        city="Recife",
        state="PE",
        country="BR",
        event_date=datetime(2027, 1, 20),
        published_at=datetime(2026, 1, 5, 8, 0, 0),
        google_news_id="recife-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        await remediate_future_event_dates(dry_run=False)

    await async_session.refresh(unique)
    await async_session.refresh(raw)
    assert unique.event_date is None
    assert unique.date_precision == "não informada"
    assert unique.merged_data["date_time"]["date"] is None
    assert raw.event_date is None
    assert raw.date_precision == "não informada"


def test_shared_clamp_helper_is_used_by_remediator_contract():
    """Remediator and extract heuristics share one pure clamp."""
    result = clamp_event_date_against_publish("2026-10-16", datetime(2026, 8, 20))
    assert result.action == "previous_year"
    assert result.date == "2025-10-16"


@pytest.mark.asyncio
async def test_remediator_skips_date_within_skew(async_session):
    unique, _raw, _source = await _seed_event(
        async_session,
        title="Homicídio recente",
        city="Salvador",
        state="BA",
        country="BR",
        event_date=datetime(2026, 8, 21),
        published_at=datetime(2026, 8, 20, 12, 0, 0),
        google_news_id="ssa-skew-228",
    )

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_future_event_dates(dry_run=False)

    await async_session.refresh(unique)
    assert unique.event_date.date().isoformat() == "2026-08-21"
    count = await async_session.execute(text("SELECT COUNT(*) FROM unique_event"))
    assert count.scalar_one() == 1
    assert audit["updated"] == 0
