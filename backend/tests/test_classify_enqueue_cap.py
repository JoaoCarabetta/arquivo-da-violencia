"""Tests for classify enqueue limits after ingest."""

from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.pipeline import ingest_cities_task


@pytest.mark.asyncio
async def test_ingest_enqueues_classify_with_capped_limit():
    ctx = {"redis": AsyncMock()}
    ingest_result = {"total_sources_created": 300, "status": "completed"}

    with (
        patch("app.tasks.pipeline.notify_job_started", new_callable=AsyncMock),
        patch("app.tasks.pipeline.notify_job_finished", new_callable=AsyncMock),
        patch(
            "app.services.ingestion.ingest_all_cities",
            new_callable=AsyncMock,
            return_value=ingest_result,
        ),
    ):
        await ingest_cities_task(ctx, when="1h", enqueue_classify=True)

    ctx["redis"].enqueue_job.assert_awaited_once_with("classify_pending_task", 200)


@pytest.mark.asyncio
async def test_ingest_enqueues_classify_with_small_batch_limit():
    ctx = {"redis": AsyncMock()}
    ingest_result = {"total_sources_created": 50, "status": "completed"}

    with (
        patch("app.tasks.pipeline.notify_job_started", new_callable=AsyncMock),
        patch("app.tasks.pipeline.notify_job_finished", new_callable=AsyncMock),
        patch(
            "app.services.ingestion.ingest_all_cities",
            new_callable=AsyncMock,
            return_value=ingest_result,
        ),
    ):
        await ingest_cities_task(ctx, when="1h", enqueue_classify=True)

    ctx["redis"].enqueue_job.assert_awaited_once_with("classify_pending_task", 100)
