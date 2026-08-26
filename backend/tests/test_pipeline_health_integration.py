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
        CRITICAL TEST per spec review: A mid-run 12-country ingest that has
        started and is making progress (has Starting multi-country ingestion +
        Starting PARALLEL city ingestion + city Done lines + INGESTION COMPLETE
        for at least one country) but NOT yet MULTI-COUNTRY INGESTION COMPLETE,
        with lock arq:in-progress:cron:ingest_cities_hourly:..., must return
        is_stale=False.
        
        This is the exact scenario from the production incident (~1072s runtime,
        never reached MULTI-COUNTRY COMPLETE before being killed).
        """
        # Simulate the in-progress lock from the production incident
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        
        # Simulate actual worker logs from a mid-run 12-country ingest
        # Using REAL log patterns from ingestion.py
        logs = WorkerLogs("""
        [2026-08-25 15:05:00] [INGEST_HOURLY] Starting hourly city ingest
        [2026-08-25 15:05:01] [INGEST_CITIES] Starting with when=1h
        [2026-08-25 15:05:02] Starting multi-country ingestion (12 countries)
        [2026-08-25 15:05:03] Starting PARALLEL city ingestion for 150 cities in BR
        [2026-08-25 15:06:00] [São Paulo] Starting...
        [2026-08-25 15:06:45] [São Paulo] Done: 40 entries, 12 new
        [2026-08-25 15:07:00] [Rio de Janeiro] Starting...
        [2026-08-25 15:07:30] [Rio de Janeiro] Done: 35 entries, 8 new
        [2026-08-25 15:08:00] [Belo Horizonte] Starting...
        [2026-08-25 15:08:25] [Belo Horizonte] Done: 28 entries, 5 new
        [2026-08-25 15:10:00] INGESTION COMPLETE (BR)
        [2026-08-25 15:10:05] Starting PARALLEL city ingestion for 45 cities in CL
        [2026-08-25 15:11:00] [Santiago] Starting...
        [2026-08-25 15:11:30] [Santiago] Done: 22 entries, 6 new
        [2026-08-25 15:21:00] INGESTION COMPLETE (CL)
        """)
        # NOTE: No MULTI-COUNTRY INGESTION COMPLETE yet - still processing remaining countries
        
        # The lock is older than 15 minutes, but it's making clear progress
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
        Remediate should NOT enqueue classify_pending while ingest_cities_hourly
        is still the active hourly task, even if queue appears jammed.
        """
        # Simulate the in-progress lock
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        
        # Simulate worker logs showing ongoing multi-country ingestion (REAL patterns)
        logs = WorkerLogs("""
        [2026-08-25 15:05:00] Starting multi-country ingestion (12 countries)
        [2026-08-25 15:06:00] Starting PARALLEL city ingestion for 150 cities in BR
        [2026-08-25 15:10:00] [São Paulo] Done: 40 entries, 12 new
        [2026-08-25 15:12:00] INGESTION COMPLETE (BR)
        [2026-08-25 15:13:00] Starting PARALLEL city ingestion for 45 cities in CL
        [2026-08-25 15:18:00] [Santiago] Done: 22 entries, 6 new
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
        CRITICAL TEST per spec review: A truly dead worker with heartbeat-only
        logs and no progress must still be remediable.
        
        Heartbeat-only logs with the same hourly lock must still be stale.
        This ensures we don't break the ability to recover from actual failures.
        """
        # Simulate a stuck lock with the same job name
        job = InProgressJob.from_redis_key(
            "arq:in-progress:cron:ingest_cities_hourly:1724594700"
        )
        
        # Heartbeat-only logs - NO actual ingestion progress
        logs = WorkerLogs("""
        [2026-08-25 14:50:00] Worker health check OK
        [2026-08-25 14:55:00] Heartbeat sent
        [2026-08-25 15:00:00] [INGEST_HOURLY] Starting hourly city ingest
        [2026-08-25 15:01:00] Heartbeat sent
        [2026-08-25 15:05:00] Heartbeat sent
        [2026-08-25 15:10:00] Heartbeat sent
        [2026-08-25 15:15:00] Heartbeat sent
        [2026-08-25 15:20:00] Heartbeat sent
        """)
        # No Starting multi-country, no Starting PARALLEL, no city Done, no INGESTION COMPLETE
        
        # Lock is 20+ minutes old with NO progress - worker is stuck/dead
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
        # No in-progress locks - ingest has completed (REAL pattern)
        logs = WorkerLogs("""
        [2026-08-25 15:22:00] MULTI-COUNTRY INGESTION COMPLETE (12 countries)
        [2026-08-25 15:22:01] Total entries: 1250
        [2026-08-25 15:22:01] Total sources: 550
        [2026-08-25 15:22:02] [INGEST_CITIES] Complete: 550 new sources
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
        # REAL pattern: city ingestion progress
        logs = WorkerLogs("[Curitiba] Done: 15 entries, 3 new")
        
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
        # REAL pattern: country completion
        logs = WorkerLogs("INGESTION COMPLETE (CL)")
        
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
        # REAL pattern: parallel city ingestion
        logs = WorkerLogs("Starting PARALLEL city ingestion for 150 cities in BR")
        
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
