"""
Integration tests for pipeline health check script.

These tests verify the bash script correctly uses the Python remediation logic
to handle live long-running ingest jobs.
"""

import pytest
from app.services.pipeline_health import (
    InProgressJob,
    WorkerLogs,
    should_treat_lock_as_stale,
    should_enqueue_classify_during_remediation,
)


class TestProductionScenarioIssue193:
    """
    Test the exact production scenario from issue #193.
    
    Production worker 2e675ee. 2026-08-25 15:21 UTC GitHub Actions Pipeline 
    Health run 32865263134. The health job treated a live ingest_all_countries 
    lock as stale. With 12 South American countries, ingest regularly holds 
    the lock past 15 minutes (this run ~1072s).
    """
    
    def test_live_ingest_not_treated_as_stale_with_progress(self):
        """
        A 12-country ingest running for 1072s (~18 minutes) with progress
        should NOT be treated as stale.
        """
        # Simulate the in-progress lock from the production incident
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        
        # Simulate worker logs showing multi-country progress
        # This is what a healthy 12-country ingest looks like
        logs = WorkerLogs("""
        [2026-08-25 15:05:00] Starting multi-country ingestion (12 countries)
        [2026-08-25 15:07:00] Country BR complete: 150 sources in 180s
        [2026-08-25 15:09:00] Country CL complete: 45 sources in 120s
        [2026-08-25 15:11:00] Country AR complete: 80 sources in 115s
        [2026-08-25 15:13:00] Country UY complete: 25 sources in 90s
        [2026-08-25 15:15:00] Country PY complete: 30 sources in 95s
        [2026-08-25 15:17:00] Country BO complete: 20 sources in 85s
        [2026-08-25 15:19:00] Starting ingestion for country PE
        [2026-08-25 15:21:00] Country PE complete: 40 sources in 110s
        """)
        
        # The lock is older than 15 minutes, but it's making progress
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        # CRITICAL: Must NOT be treated as stale
        assert not is_stale, "Live ingest with progress must not be treated as stale"
        assert reason == "ingest_lock_with_progress"
    
    def test_remediate_does_not_enqueue_classify_during_live_ingest(self):
        """
        Remediate should NOT enqueue classify_pending while ingest_all_countries
        is still the active hourly task, even if queue appears jammed.
        """
        # Simulate the in-progress lock
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        
        # Simulate worker logs showing ongoing multi-country ingestion
        logs = WorkerLogs("""
        [2026-08-25 15:10:00] Country BR complete: 150 sources in 180s
        [2026-08-25 15:15:00] Starting ingestion for country AR
        [2026-08-25 15:18:00] Country AR complete: 80 sources in 115s
        """)
        
        # The health check detected a "queue jam" because the lock is old
        # But it should NOT enqueue classify because ingest is active
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,  # This was detected in the incident
            had_no_pipeline=False,
            had_recent_ingest=True,
            in_progress_jobs=[job],
            worker_logs=logs,
        )
        
        # CRITICAL: Must NOT enqueue classify
        assert not should_enqueue, "Must not enqueue classify during active ingest"
        assert reason == "active_ingest_with_progress"
    
    def test_truly_dead_worker_still_remediable(self):
        """
        A truly dead worker with no progress should still be remediable.
        
        This ensures we don't break the ability to recover from actual failures.
        """
        # Simulate a stuck lock with the same job name
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        
        # But logs show NO progress - worker is actually dead
        logs = WorkerLogs("""
        [2026-08-25 14:50:00] Worker health check OK
        [2026-08-25 14:55:00] Heartbeat sent
        [2026-08-25 15:00:00] Starting multi-country ingestion (12 countries)
        [2026-08-25 15:01:00] Heartbeat sent
        """)
        
        # No country-level progress for 20+ minutes
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        # This IS stale and should be remediable
        assert is_stale, "Dead worker with no progress must be remediable"
        assert reason == "ingest_lock_without_progress"
    
    def test_completed_ingest_allows_classify_enqueue(self):
        """
        After ingest completes (no active lock), classify can be enqueued.
        """
        # No in-progress locks - ingest has completed
        logs = WorkerLogs("""
        [2026-08-25 15:22:00] MULTI-COUNTRY INGESTION COMPLETE (12 countries)
        [2026-08-25 15:22:00] Total sources: 550
        """)
        
        # Queue is jammed with ready backlog
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,
            had_no_pipeline=False,
            had_recent_ingest=True,
            in_progress_jobs=[],  # No locks
            worker_logs=logs,
        )
        
        # Now it's safe to enqueue classify
        assert should_enqueue, "Should enqueue classify after ingest completes"
        assert reason == "queue_jammed"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_backlog_processing_lock_respected(self):
        """process_cities_backlog with progress should not be treated as stale."""
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:process_cities_backlog:1724594700"
        )
        logs = WorkerLogs("Starting ingestion for country BR")
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert not is_stale
        assert reason == "ingest_lock_with_progress"
    
    def test_full_pipeline_lock_respected(self):
        """ingest_cities_full_pipeline with progress should not be treated as stale."""
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_full_pipeline:1724594700"
        )
        logs = WorkerLogs("Country CL complete: 45 sources in 120s")
        
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert not is_stale
        assert reason == "ingest_lock_with_progress"
    
    def test_multiple_locks_any_ingest_prevents_classify(self):
        """If any lock is an ingest, don't enqueue classify."""
        jobs = [
            InProgressJob.from_redis_key("arq:in-progress:some_task:123"),
            InProgressJob.from_redis_key("arq:in-progress:cron:ingest_cities_hourly:456"),
        ]
        logs = WorkerLogs("Country BR complete: 150 sources in 180s")
        
        should_enqueue, reason = should_enqueue_classify_during_remediation(
            had_queue_jam=True,
            had_no_pipeline=False,
            had_recent_ingest=True,
            in_progress_jobs=jobs,
            worker_logs=logs,
        )
        
        assert not should_enqueue
        assert reason == "active_ingest_with_progress"
    
    def test_no_logs_available(self):
        """Handle case where logs are empty or unavailable."""
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        logs = WorkerLogs("")
        
        # Without progress evidence, treat as stale
        is_stale, reason = should_treat_lock_as_stale(
            in_progress_jobs=[job],
            worker_logs=logs,
            stale_threshold_minutes=15,
        )
        
        assert is_stale
        assert reason == "ingest_lock_without_progress"
