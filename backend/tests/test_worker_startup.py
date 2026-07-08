"""Tests for worker startup recovery helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.worker import purge_stale_arq_in_progress


@pytest.mark.asyncio
async def test_purge_stale_arq_in_progress_deletes_matching_keys():
    redis = AsyncMock()
    redis.scan = AsyncMock(side_effect=[
        (0, [b"arq:in-progress:abc", b"arq:in-progress:cron:ingest_cities_hourly:1"]),
    ])
    redis.delete = AsyncMock()

    removed = await purge_stale_arq_in_progress(redis)

    assert removed == 2
    assert redis.delete.await_count == 2


@pytest.mark.asyncio
async def test_purge_stale_arq_in_progress_no_keys():
    redis = AsyncMock()
    redis.scan = AsyncMock(return_value=(0, []))

    removed = await purge_stale_arq_in_progress(redis)

    assert removed == 0
    redis.delete.assert_not_called()
