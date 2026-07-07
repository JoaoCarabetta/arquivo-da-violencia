"""Tests for ARQ worker cron configuration."""

from unittest.mock import patch

from app.tasks.worker import get_cron_jobs, is_cron_enabled


def test_is_cron_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_CRON", raising=False)
    assert is_cron_enabled() is False


def test_is_cron_enabled_true_when_set(monkeypatch):
    monkeypatch.setenv("ENABLE_CRON", "true")
    assert is_cron_enabled() is True


def test_get_cron_jobs_empty_when_disabled():
    with patch("app.tasks.worker.is_cron_enabled", return_value=False):
        assert get_cron_jobs() == []


def test_get_cron_jobs_split_ingest_and_backlog_when_enabled():
    with patch("app.tasks.worker.is_cron_enabled", return_value=True):
        jobs = get_cron_jobs()

    assert len(jobs) == 2

    by_name = {job.coroutine.__name__: job for job in jobs}
    assert "ingest_cities_hourly" in by_name
    assert "process_cities_backlog" in by_name

    ingest = by_name["ingest_cities_hourly"]
    backlog = by_name["process_cities_backlog"]

    assert ingest.minute == 5
    assert ingest.timeout_s == 1800
    assert ingest.unique is True

    assert backlog.minute == 35
    assert backlog.timeout_s == 7200
    assert backlog.unique is True
