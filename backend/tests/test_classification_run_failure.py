"""Tests for classification run failure on high model-call error rate (issue #279)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.classification_run import (
    MODEL_CALL_ERROR_FAIL_MIN_CALLS,
    ClassificationRunModelCallFailure,
    ClassificationRunStats,
    raise_if_classification_run_failed,
    should_fail_classification_run,
)
from app.tasks.pipeline import (
    _process_cities_backlog_steps,
    _run_classify_until_drained,
    process_cities_backlog,
)


class TestClassificationRunThreshold:
    def test_all_fail_meets_threshold(self):
        n = MODEL_CALL_ERROR_FAIL_MIN_CALLS
        stats = ClassificationRunStats(
            violent_death=0, discarded=0, model_call_errors=n
        )
        assert stats.model_call_attempts == n
        assert should_fail_classification_run(stats) is True

    def test_few_fail_below_threshold(self):
        stats = ClassificationRunStats(
            violent_death=47, discarded=0, model_call_errors=3
        )
        assert stats.model_call_attempts == 50
        assert stats.model_call_error_rate == 0.06
        assert should_fail_classification_run(stats) is False

    def test_high_rate_but_too_few_calls(self):
        stats = ClassificationRunStats(
            violent_death=0, discarded=0, model_call_errors=10
        )
        assert should_fail_classification_run(stats) is False

    def test_raise_includes_first_error_snippet(self):
        stats = ClassificationRunStats(
            violent_death=0, discarded=0, model_call_errors=50
        )
        with pytest.raises(ClassificationRunModelCallFailure) as exc_info:
            raise_if_classification_run_failed(
                stats, "402 Insufficient credits"
            )
        assert "model_call_errors=50" in str(exc_info.value)
        assert "402" in str(exc_info.value)

    def test_redacts_bearer_in_error_snippet(self):
        stats = ClassificationRunStats(
            violent_death=0, discarded=0, model_call_errors=50
        )
        with pytest.raises(ClassificationRunModelCallFailure) as exc_info:
            raise_if_classification_run_failed(
                stats,
                "HTTP 401 Bearer sk-testsecret1234567890",
            )
        msg = str(exc_info.value)
        assert "sk-testsecret" not in msg
        assert "Bearer sk-" not in msg


@pytest.mark.asyncio
async def test_run_classify_until_drained_returns_totals_on_all_fail_batch():
    batch_stats = {
        "processed": 150,
        "violent_death": 0,
        "discarded": 0,
        "errors": 150,
        "model_call_errors": 150,
        "other_errors": 0,
        "first_model_call_error": "402 Insufficient credits",
    }

    with patch(
        "app.services.classification.classify_pending_sources",
        new_callable=AsyncMock,
        return_value=batch_stats,
    ) as mock_classify:
        result = await _run_classify_until_drained(
            limit_per_batch=150, max_batches=1, concurrency=1
        )
        mock_classify.assert_awaited_once()

    assert result["model_call_errors"] == 150
    assert result["first_model_call_error"] == "402 Insufficient credits"


@pytest.mark.asyncio
async def test_run_classify_until_drained_completes_on_few_fail_batch():
    batch_stats = {
        "processed": 100,
        "violent_death": 90,
        "discarded": 7,
        "errors": 3,
        "model_call_errors": 3,
        "other_errors": 0,
        "first_model_call_error": "402 Insufficient credits",
    }

    with patch(
        "app.services.classification.classify_pending_sources",
        new_callable=AsyncMock,
        return_value=batch_stats,
    ):
        result = await _run_classify_until_drained(
            limit_per_batch=150, max_batches=1, concurrency=1
        )

    assert result["model_call_errors"] == 3
    assert result["violent_death"] == 90


@pytest.mark.asyncio
async def test_process_cities_backlog_steps_runs_downstream_before_failure():
    ctx = {}
    classify_totals = {
        "processed": 150,
        "violent_death": 0,
        "discarded": 0,
        "errors": 150,
        "model_call_errors": 150,
        "other_errors": 0,
        "first_model_call_error": "402 Insufficient credits",
    }

    with (
        patch(
            "app.tasks.pipeline._run_classify_until_drained",
            new_callable=AsyncMock,
            return_value=classify_totals,
        ) as mock_classify,
        patch(
            "app.tasks.pipeline.download_classified_task",
            new_callable=AsyncMock,
            return_value={"successful": 0},
        ) as mock_download,
        patch(
            "app.tasks.pipeline.extract_ready_task",
            new_callable=AsyncMock,
            return_value={"raw_events_created": 0},
        ) as mock_extract,
        patch(
            "app.tasks.pipeline.batch_dedup_task",
            new_callable=AsyncMock,
            return_value={"unique_events_created": 0},
        ) as mock_dedup,
        patch(
            "app.tasks.pipeline.batch_enrich_task",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_enrich,
        patch(
            "app.tasks.pipeline.batch_geocode_task",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_geocode,
    ):
        with pytest.raises(ClassificationRunModelCallFailure):
            await _process_cities_backlog_steps(ctx)

    mock_classify.assert_awaited_once()
    mock_download.assert_awaited_once()
    mock_extract.assert_awaited_once()
    mock_dedup.assert_awaited_once()
    mock_enrich.assert_awaited_once()
    mock_geocode.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_cities_backlog_propagates_classification_run_failure():
    ctx = {}

    with (
        patch(
            "app.tasks.pipeline._run_pipeline_maintenance",
            new_callable=AsyncMock,
        ),
        patch(
            "app.tasks.pipeline.notify_job_started",
            new_callable=AsyncMock,
        ),
        patch(
            "app.tasks.pipeline._process_cities_backlog_steps",
            new_callable=AsyncMock,
            side_effect=ClassificationRunModelCallFailure("simulated"),
        ),
        patch(
            "app.tasks.pipeline.notify_job_failed",
            new_callable=AsyncMock,
        ) as mock_failed,
        patch(
            "app.tasks.pipeline.create_failure_issue",
            new_callable=AsyncMock,
        ) as mock_issue,
    ):
        with pytest.raises(ClassificationRunModelCallFailure):
            await process_cities_backlog(ctx)

    mock_failed.assert_awaited_once()
    mock_issue.assert_awaited_once()
