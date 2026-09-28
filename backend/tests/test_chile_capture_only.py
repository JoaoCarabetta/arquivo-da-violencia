"""Chile (and other) history-only capture: separate queue, no BR process path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.country_registry import ALL_COUNTRIES
from app.models.source_google_news import SourceStatus


_INGEST_DUMMY = {
    "country": "XX",
    "cities_processed": 0,
    "total_entries": 0,
    "total_sources_created": 0,
    "errors": 0,
    "elapsed_seconds": 0,
    "city_results": {},
}


class TestCaptureCountrySettings:
    def test_defaults_to_empty_list(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_CAPTURE_COUNTRIES", raising=False)
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.pipeline_capture_countries == []

    def test_loads_json_list_from_env(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_CAPTURE_COUNTRIES", '["CL"]')
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.pipeline_capture_countries == ["CL"]

    def test_capture_countries_excluded_from_active(self):
        from app.config import get_pipeline_active_countries, get_pipeline_capture_countries

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.pipeline_active_countries = []
            mock_settings.return_value.pipeline_capture_countries = ["CL"]
            active = get_pipeline_active_countries()
            capture = get_pipeline_capture_countries()

        assert capture == ["CL"]
        assert "CL" not in active
        assert "BR" in active
        assert len(active) == len(ALL_COUNTRIES) - 1

    def test_br_only_active_unchanged_when_capture_cl(self):
        from app.config import get_pipeline_active_countries

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.pipeline_active_countries = ["BR"]
            mock_settings.return_value.pipeline_capture_countries = ["CL"]
            assert get_pipeline_active_countries() == ["BR"]


class TestCaptureQueueIsolation:
    def test_capture_queue_name_differs_from_process_queue(self):
        from app.tasks.worker import get_arq_capture_queue_name, get_arq_queue_name

        process_q = get_arq_queue_name()
        capture_q = get_arq_capture_queue_name()
        assert capture_q != process_q
        assert capture_q.endswith(":capture")
        assert process_q + ":capture" == capture_q

    def test_capture_worker_functions_exclude_classify(self):
        from app.tasks.pipeline import CAPTURE_TASK_FUNCTIONS, TASK_FUNCTIONS

        def _names(funcs):
            out = []
            for f in funcs:
                out.append(getattr(f, "name", None) or getattr(f, "__name__", str(f)))
            return out

        capture_names = _names(CAPTURE_TASK_FUNCTIONS)
        process_names = _names(TASK_FUNCTIONS)

        assert any("capture" in n for n in capture_names)
        assert not any("classify" in n for n in capture_names)
        assert not any("download" in n for n in capture_names)
        assert not any("extract" in n for n in capture_names)
        # Capture tasks must not be registered on the BR worker.
        assert not any("capture" in n for n in process_names)

    def test_capture_worker_settings_use_capture_queue(self):
        from app.tasks.worker import CaptureWorkerSettings, WorkerSettings, get_arq_capture_queue_name

        assert CaptureWorkerSettings.queue_name == get_arq_capture_queue_name()
        assert WorkerSettings.queue_name != CaptureWorkerSettings.queue_name


class TestIngestCaptureCountries:
    @pytest.mark.asyncio
    async def test_ingest_capture_uses_captured_status_and_cl_only(self):
        from app.services.ingestion import ingest_capture_countries

        with (
            patch(
                "app.services.ingestion.ingest_all_cities",
                new_callable=AsyncMock,
                return_value=_INGEST_DUMMY,
            ) as mock_ingest,
            patch(
                "app.services.ingestion.get_pipeline_capture_countries",
                return_value=["CL"],
            ),
        ):
            result = await ingest_capture_countries(when="1h", resolve_urls=False)

        assert mock_ingest.await_count == 1
        kwargs = mock_ingest.await_args.kwargs
        assert kwargs["country"] == "CL"
        assert kwargs["source_status"] == SourceStatus.captured
        assert result["mode"] == "capture_only"
        assert set(result["countries"].keys()) == {"CL"}

    @pytest.mark.asyncio
    async def test_ingest_capture_empty_is_noop(self):
        from app.services.ingestion import ingest_capture_countries

        with (
            patch(
                "app.services.ingestion.ingest_all_cities",
                new_callable=AsyncMock,
            ) as mock_ingest,
            patch(
                "app.services.ingestion.get_pipeline_capture_countries",
                return_value=[],
            ),
        ):
            result = await ingest_capture_countries(when="1h")

        mock_ingest.assert_not_awaited()
        assert result["total_sources_created"] == 0
        assert result["mode"] == "capture_only"

    @pytest.mark.asyncio
    async def test_active_ingest_skips_capture_country(self):
        from app.services.ingestion import ingest_all_countries

        with (
            patch(
                "app.services.ingestion.ingest_all_cities",
                new_callable=AsyncMock,
                return_value=_INGEST_DUMMY,
            ) as mock_ingest,
            patch(
                "app.services.ingestion.get_pipeline_active_countries",
                return_value=["BR"],
            ),
        ):
            result = await ingest_all_countries(when="1h", resolve_urls=False)

        countries = [c.kwargs["country"] for c in mock_ingest.await_args_list]
        assert countries == ["BR"]
        assert "CL" not in countries
        # Process path must keep default ready_for_classification.
        for call in mock_ingest.await_args_list:
            assert call.kwargs.get("source_status", SourceStatus.ready_for_classification) == (
                SourceStatus.ready_for_classification
            )
        assert set(result["countries"].keys()) == {"BR"}


class TestCaptureTaskNeverEnqueuesClassify:
    @pytest.mark.asyncio
    async def test_ingest_capture_task_does_not_enqueue_classify(self):
        from app.tasks.pipeline import ingest_capture_countries_task

        redis = MagicMock()
        redis.enqueue_job = AsyncMock()
        ctx = {"redis": redis}

        with patch(
            "app.services.ingestion.ingest_capture_countries",
            new_callable=AsyncMock,
            return_value={
                "total_sources_created": 12,
                "total_entries": 20,
                "elapsed_seconds": 1.0,
                "countries": {"CL": {}},
                "mode": "capture_only",
            },
        ):
            with (
                patch("app.tasks.pipeline.notify_job_started", new_callable=AsyncMock),
                patch("app.tasks.pipeline.notify_job_finished", new_callable=AsyncMock),
            ):
                result = await ingest_capture_countries_task(ctx, when="1h")

        redis.enqueue_job.assert_not_awaited()
        assert result["task"] == "ingest_capture_countries"
        assert result["total_sources_created"] == 12
        assert result["mode"] == "capture_only"
