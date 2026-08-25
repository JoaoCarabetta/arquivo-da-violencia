"""Tests for pipeline health check and remediation logic."""

import pytest
from datetime import datetime, timezone

from app.services.pipeline_health import (
    InProgressJob,
    WorkerLogs,
    should_treat_lock_as_stale,
    should_enqueue_classify_during_remediation,
)


class TestInProgressJob:
    """Tests for InProgressJob parsing."""
    
    def test_parse_cron_job_key_with_timestamp(self):
        """Parse a cron job key with timestamp."""
        key = "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        job = InProgressJob.from_redis_key(key)
        
        assert job.key == key
        assert job.job_name == "ingest_cities_hourly"
        assert job.enqueued_at == datetime.fromtimestamp(1724594700, tz=timezone.utc)
    
    def test_parse_cron_job_key_without_timestamp(self):
        """Parse a cron job key without timestamp."""
        key = "arq:in-progress:cron:process_cities_backlog"
        job = InProgressJob.from_redis_key(key)
        
        assert job.key == key
        assert job.job_name == "process_cities_backlog"
        assert job.enqueued_at is None
    
    def test_parse_non_cron_job_key(self):
        """Parse a non-cron job key."""
        key = "arq:in-progress:abc123def456"
        job = InProgressJob.from_redis_key(key)
        
        assert job.key == key
        assert job.job_name == "unknown"
        assert job.enqueued_at is None


class TestWorkerLogs:
    """Tests for WorkerLogs progress detection using ACTUAL log patterns."""
    
    def test_detects_multi_country_start(self):
        """Detect multi-country ingestion start (actual pattern)."""
        logs = WorkerLogs("""
        [2026-08-25 15:05:00] Starting multi-country ingestion (12 countries)
        """)
        
        assert logs.has_multi_country_ingest_progress()
    
    def test_detects_parallel_city_ingestion(self):
        """Detect parallel city ingestion start (actual pattern)."""
        logs = WorkerLogs("""
        [2026-08-25 15:06:00] Starting PARALLEL city ingestion for 150 cities in BR
        """)
        
        assert logs.has_multi_country_ingest_progress()
    
    def test_detects_city_done(self):
        """Detect individual city completion (actual pattern)."""
        logs = WorkerLogs("""
        [2026-08-25 15:10:00] [São Paulo] Done: 40 entries, 12 new
        """)
        
        assert logs.has_multi_country_ingest_progress()
    
    def test_detects_country_completion(self):
        """Detect country-level completion (actual pattern)."""
        logs = WorkerLogs("""
        [2026-08-25 15:12:00] INGESTION COMPLETE (BR)
        """)
        
        assert logs.has_multi_country_ingest_progress()
    
    def test_no_progress_in_generic_logs(self):
        """No progress detected in generic worker logs."""
        logs = WorkerLogs("""
        [2026-08-25 15:08:00] Worker health check OK
        [2026-08-25 15:09:00] Heartbeat sent
        """)
        
        assert not logs.has_multi_country_ingest_progress()


class TestShouldTreatLockAsStale:
    """
    Tests for stale lock detection.
    
    CRITICAL: These tests verify the fix for issue #193.
    """
    
    def test_no_locks_not_stale(self):
        """No locks means nothing is stale."""
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[],
            worker_logs=WorkerLogs(""),
            stale_threshold_minutes=15,
        )
        
        assert not is_stale
        assert reason == "no_locks"
    
    def test_non_ingest_lock_is_stale(self):
        """Non-ingest locks are treated as stale."""
        job = InProgressJob.from_redis_key("arq:in-progress:cron:some_other_task:123")
        logs = WorkerLogs("")
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert is_stale
        assert reason == "non_ingest_lock_present"
    
    def test_ingest_lock_with_progress_not_stale(self):
        """
        CRITICAL: Ingest lock with progress is NOT stale, even if > 15 minutes.
        
        This is the core fix for issue #193. A 12-country ingest that takes
        ~1072s (~18 minutes) should not be killed if it's making progress.
        """
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        # REAL patterns from actual logs
        logs = WorkerLogs("""
        [2026-08-25 15:05:00] Starting multi-country ingestion (12 countries)
        [2026-08-25 15:06:00] Starting PARALLEL city ingestion for 150 cities in BR
        [2026-08-25 15:10:00] [São Paulo] Done: 40 entries, 12 new
        [2026-08-25 15:12:00] INGESTION COMPLETE (BR)
        [2026-08-25 15:13:00] Starting PARALLEL city ingestion for 45 cities in CL
        [2026-08-25 15:14:00] [Santiago] Done: 22 entries, 6 new
        """)
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert not is_stale
        assert reason == "ingest_lock_with_progress"
    
    def test_ingest_lock_without_progress_is_stale(self):
        """
        Ingest lock without progress IS stale.
        
        A truly dead worker should still be remediable.
        """
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        logs = WorkerLogs("""
        [2026-08-25 14:50:00] Worker health check OK
        [2026-08-25 14:55:00] Heartbeat sent
        """)
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert is_stale
        assert reason == "ingest_lock_without_progress"
    
    def test_full_pipeline_lock_with_progress_not_stale(self):
        """Full pipeline job with progress is not stale."""
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_full_pipeline:1724594700"
        )
        # REAL pattern: city completion
        logs = WorkerLogs("[Porto Alegre] Done: 18 entries, 4 new")
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert not is_stale
        assert reason == "ingest_lock_with_progress"
    
    def test_backlog_processing_with_progress_not_stale(self):
        """Backlog processing with progress is not stale."""
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:process_cities_backlog:1724594700"
        )
        # REAL pattern: multi-country start
        logs = WorkerLogs("Starting multi-country ingestion (12 countries)")
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert not is_stale
        assert reason == "ingest_lock_with_progress"


class TestShouldEnqueueClassifyDuringRemediation:
    """
    Tests for classify enqueue decision during remediation.
    
    CRITICAL: These tests verify we don't enqueue classify while ingest is active.
    """
    
    def test_no_enqueue_when_ingest_active_with_progress(self):
        """
        CRITICAL: Do NOT enqueue classify when ingest is active and making progress.
        
        This prevents the issue where remediate enqueued classify_pending while
        ingest_cities_hourly was still the active hourly task.
        """
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        # REAL pattern: parallel city ingestion
        logs = WorkerLogs("Starting PARALLEL city ingestion for 150 cities in BR")
        
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,  # Even with queue jam
            had_no_pipeline=False,
            had_recent_ingest=True,
            in_progress_jobs=[job],
            worker_logs=logs,
        )
        
        assert not should_enqueue
        assert reason == "active_ingest_with_progress"
    
    def test_no_enqueue_when_ingest_lock_present_without_progress(self):
        """
        Do NOT enqueue classify when ingest lock is present, even without progress.
        
        Let other remediation (worker restart, lock clear) handle the stuck ingest.
        """
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        logs = WorkerLogs("No progress logs here")
        
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,
            had_no_pipeline=False,
            had_recent_ingest=True,
            in_progress_jobs=[job],
            worker_logs=logs,
        )
        
        assert not should_enqueue
        assert reason == "active_ingest_lock_present"
    
    def test_enqueue_when_queue_jammed_without_ingest(self):
        """Enqueue classify when queue is jammed and no ingest is active."""
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,
            had_no_pipeline=False,
            had_recent_ingest=False,
            in_progress_jobs=[],
            worker_logs=WorkerLogs(""),
        )
        
        assert should_enqueue
        assert reason == "queue_jammed"
    
    def test_enqueue_when_no_pipeline_with_recent_ingest(self):
        """Enqueue classify when no pipeline but recent ingest (and no active lock)."""
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=False,
            had_no_pipeline=True,
            had_recent_ingest=True,
            in_progress_jobs=[],
            worker_logs=WorkerLogs(""),
        )
        
        assert should_enqueue
        assert reason == "no_pipeline_with_recent_ingest"
    
    def test_no_enqueue_when_no_conditions_met(self):
        """Do not enqueue classify when no conditions are met."""
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=False,
            had_no_pipeline=False,
            had_recent_ingest=False,
            in_progress_jobs=[],
            worker_logs=WorkerLogs(""),
        )
        
        assert not should_enqueue
        assert reason == "no_condition_met"
    
    def test_no_enqueue_full_pipeline_with_progress(self):
        """Do not enqueue classify when full pipeline is active with progress."""
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_full_pipeline:1724594700"
        )
        # REAL pattern: country completion
        logs = WorkerLogs("INGESTION COMPLETE (AR)")
        
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,
            had_no_pipeline=False,
            had_recent_ingest=True,
            in_progress_jobs=[job],
            worker_logs=logs,
        )
        
        assert not should_enqueue
        assert reason == "active_ingest_with_progress"
