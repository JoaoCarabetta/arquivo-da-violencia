"""Telegram/notify failure must not freeze or abort batch_dedup (#220)."""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.models.raw_event import RawEvent
from app.services.enrichment import (
    create_unique_event_from_cluster,
    process_pending_deduplication,
)
from app.services.telegram import TelegramNotifier

PENDING_COUNT = 10
CITIES = [
    "Recife",
    "Várzea Grande",
    "Zumbi dos Palmares",
    "Manaus",
    "Belém",
    "Fortaleza",
    "Salvador",
    "Natal",
    "Maceió",
    "João Pessoa",
]


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _pending_raw_events() -> list[RawEvent]:
    return [
        RawEvent(
            title=f"HOMICÍDIO - {city.upper()} - 03/09/2026",
            event_date=datetime(2026, 9, 3),
            city=city,
            state="BR",
            country="BR",
            victim_count=1,
            source_google_news_id=2000 + idx,
            deduplication_status="pending",
            chronological_description=f"Uma pessoa morreu em {city}.",
        )
        for idx, city in enumerate(CITIES)
    ]


async def _count_unique_events(session) -> int:
    result = await session.execute(text("SELECT COUNT(*) FROM unique_event"))
    return int(result.scalar_one())


async def _count_pending_raw_events(session) -> int:
    result = await session.execute(
        text("SELECT COUNT(*) FROM raw_event WHERE deduplication_status = 'pending'")
    )
    return int(result.scalar_one())


@pytest.mark.asyncio
async def test_batch_dedup_creates_all_unique_events_when_notify_raises(async_session):
    """A lot of ≥10 pending clusters must finish even if notify_new_death raises every time."""
    events = _pending_raw_events()
    async_session.add_all(events)
    await async_session.commit()
    for event in events:
        await async_session.refresh(event)

    notify_mock = AsyncMock(side_effect=TimeoutError())

    with (
        patch(
            "app.services.enrichment.async_session_maker",
            _TestSessionMaker(async_session),
        ),
        patch(
            "app.services.enrichment.notify_new_death",
            notify_mock,
        ),
        patch(
            "app.services.enrichment._merge_near_duplicates_in_buckets",
            AsyncMock(return_value=0),
        ),
    ):
        result = await process_pending_deduplication(limit=20)

    assert result["status"] == "completed"
    assert result["unique_events_created"] == PENDING_COUNT
    assert result["processed"] == PENDING_COUNT
    assert await _count_unique_events(async_session) == PENDING_COUNT
    assert await _count_pending_raw_events(async_session) == 0
    assert notify_mock.await_count == PENDING_COUNT


@pytest.mark.asyncio
async def test_create_unique_event_from_cluster_survives_notify_raise(async_session):
    """UniqueEvent commit must succeed when notify_new_death raises TimeoutError."""
    raw_event = _pending_raw_events()[0]
    async_session.add(raw_event)
    await async_session.commit()
    await async_session.refresh(raw_event)

    raw_event_id = raw_event.id
    with (
        patch(
            "app.services.enrichment.async_session_maker",
            _TestSessionMaker(async_session),
        ),
        patch(
            "app.services.enrichment.notify_new_death",
            AsyncMock(side_effect=TimeoutError("telegram hung")),
        ),
    ):
        unique_event = await create_unique_event_from_cluster([raw_event])

    assert unique_event.id is not None
    assert await _count_unique_events(async_session) == 1
    clustered = await async_session.execute(
        text("SELECT deduplication_status FROM raw_event WHERE id = :id"),
        {"id": raw_event_id},
    )
    assert clustered.scalar_one() == "clustered"


@pytest.mark.asyncio
async def test_create_unique_event_from_cluster_does_not_wait_on_slow_notify(
    async_session,
):
    """Slow Telegram must not serialize into UniqueEvent create for more than a short cap."""
    raw_event = _pending_raw_events()[1]
    async_session.add(raw_event)
    await async_session.commit()
    await async_session.refresh(raw_event)

    async def slow_notify(**kwargs):
        await asyncio.sleep(10)
        raise TimeoutError("still hanging")

    started = time.perf_counter()
    with (
        patch(
            "app.services.enrichment.async_session_maker",
            _TestSessionMaker(async_session),
        ),
        patch(
            "app.services.enrichment.notify_new_death",
            slow_notify,
        ),
    ):
        unique_event = await create_unique_event_from_cluster([raw_event])
    elapsed = time.perf_counter() - started

    assert unique_event.id is not None
    assert elapsed < 3.0, f"create blocked on Telegram for {elapsed:.2f}s"
    assert await _count_unique_events(async_session) == 1


@pytest.mark.asyncio
async def test_send_message_returns_false_on_timeout_error():
    """httpx/asyncio TimeoutError must not escape send_message."""
    notifier = TelegramNotifier.__new__(TelegramNotifier)
    notifier.bot_token = "token"
    notifier.chat_id = "123"
    notifier.enabled = True

    class _BoomClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise TimeoutError()

    with patch("app.services.telegram.httpx.AsyncClient", return_value=_BoomClient()):
        result = await notifier.send_message("hello")

    assert result is False
