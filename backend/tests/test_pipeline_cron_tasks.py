"""Tests for split hourly ingest / backlog cron tasks."""

from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.pipeline import (
    ingest_cities_hourly,
    process_cities_backlog,
)


@pytest.mark.asyncio
async def test_ingest_cities_hourly_does_not_enqueue_classify():
    ctx = {"redis": AsyncMock()}
    ingest_result = {"total_sources_created": 3, "status": "completed"}

    with (
        patch(
            "app.tasks.pipeline._run_pipeline_maintenance",
            new_callable=AsyncMock,
        ) as mock_maint,
        patch(
            "app.tasks.pipeline.ingest_cities_task",
            new_callable=AsyncMock,
            return_value=ingest_result,
        ) as mock_ingest,
    ):
        result = await ingest_cities_hourly(ctx, when="1h")

    mock_maint.assert_awaited_once()
    mock_ingest.assert_awaited_once_with(
        ctx, cities=None, when="1h", enqueue_classify=False
    )
    assert result == ingest_result
    ctx["redis"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_process_cities_backlog_runs_maintenance_and_steps():
    ctx = {}
    steps = {
        "classify": {"violent_death": 2, "processed": 10},
        "download": {"successful": 1},
        "extract": {"raw_events_created": 1},
        "dedup": {"unique_events_created": 1},
        "enrich": {},
        "geocode": {},
    }

    with (
        patch(
            "app.tasks.pipeline._run_pipeline_maintenance",
            new_callable=AsyncMock,
        ) as mock_maint,
        patch(
            "app.tasks.pipeline._process_cities_backlog_steps",
            new_callable=AsyncMock,
            return_value=steps,
        ) as mock_steps,
        patch(
            "app.tasks.pipeline.notify_job_started",
            new_callable=AsyncMock,
        ),
        patch(
            "app.tasks.pipeline.notify_pipeline_summary",
            new_callable=AsyncMock,
        ) as mock_summary,
    ):
        result = await process_cities_backlog(ctx)

    mock_maint.assert_awaited_once()
    mock_steps.assert_awaited_once_with(ctx)
    mock_summary.assert_awaited_once()
    assert result["task"] == "process_cities_backlog"
    assert result["status"] == "completed"
    assert result["classify"]["violent_death"] == 2
