"""Tests for pipeline health check and remediation logic."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.pipeline_health import (
    InProgressJob,
    WorkerLogs,
    bash_bool_to_python_literal,
    remediator_enqueue_followup,
    should_enqueue_classify_during_remediation,
    should_treat_lock_as_stale,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_SCRIPT = REPO_ROOT / "scripts" / "check-pipeline-health.sh"


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


class TestBashBoolToPythonLiteral:
    """Convert bash true/false so unquoted heredoc interpolation is valid Python (issue #224)."""

    def test_false_becomes_python_false(self):
        assert bash_bool_to_python_literal("false") == "False"

    def test_true_becomes_python_true(self):
        assert bash_bool_to_python_literal("true") == "True"

    def test_rejects_other_values(self):
        with pytest.raises(ValueError):
            bash_bool_to_python_literal("False")


class TestRemediatorEnqueueFollowup:
    """
    Issue #224: a failed classify-enqueue decide must not silently enqueue pipeline.

    The elif had_no_pipeline || had_stale_ingest branch may run only after a clean
    enqueue=False decision.
    """

    def test_error_decision_does_not_enqueue_pipeline_when_no_pipeline(self):
        action = remediator_enqueue_followup(
            "enqueue=error;reason=check_failed",
            had_no_pipeline=True,
            had_stale_ingest=False,
        )
        assert action == "error"

    def test_error_decision_does_not_enqueue_pipeline_when_stale_ingest(self):
        action = remediator_enqueue_followup(
            "enqueue=error;reason=check_failed",
            had_no_pipeline=False,
            had_stale_ingest=True,
        )
        assert action == "error"

    def test_empty_or_traceback_decision_is_error_not_pipeline(self):
        traceback = "NameError: name 'false' is not defined\nenqueue=error;reason=check_failed"
        assert (
            remediator_enqueue_followup(
                traceback, had_no_pipeline=True, had_stale_ingest=True
            )
            == "error"
        )
        assert remediator_enqueue_followup("", had_no_pipeline=True, had_stale_ingest=True) == "error"

    def test_clean_false_with_no_pipeline_enqueues_pipeline(self):
        action = remediator_enqueue_followup(
            "enqueue=False;reason=no_condition_met",
            had_no_pipeline=True,
            had_stale_ingest=False,
        )
        assert action == "pipeline"

    def test_clean_false_with_stale_ingest_enqueues_pipeline(self):
        action = remediator_enqueue_followup(
            "enqueue=False;reason=no_condition_met",
            had_no_pipeline=False,
            had_stale_ingest=True,
        )
        assert action == "pipeline"

    def test_clean_false_without_pipeline_flags_skips(self):
        action = remediator_enqueue_followup(
            "enqueue=False;reason=no_condition_met",
            had_no_pipeline=False,
            had_stale_ingest=False,
        )
        assert action == "skip"

    def test_clean_true_enqueues_classify(self):
        action = remediator_enqueue_followup(
            "enqueue=True;reason=queue_jammed",
            had_no_pipeline=True,
            had_stale_ingest=True,
        )
        assert action == "classify"


class TestRemediatorBoolInterpolation:
    """The unquoted <<PY heredoc must not see bash lowercase true/false (issue #224)."""

    def test_py_bool_false_flags_do_not_nameerror(self):
        """All three remediator flags as bash false interpolate as Python False."""
        script = r"""
        py_bool() { [ "$1" = true ] && echo True || echo False; }
        had_queue_jam_py=$(py_bool false)
        had_no_pipeline_py=$(py_bool false)
        had_recent_ingest_py=$(py_bool false)
        python3 - <<PY
had_queue_jam = ${had_queue_jam_py}
had_no_pipeline = ${had_no_pipeline_py}
had_recent_ingest = ${had_recent_ingest_py}
assert had_queue_jam is False
assert had_no_pipeline is False
assert had_recent_ingest is False
print("ok")
PY
        """
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"
        assert "NameError" not in result.stderr

    def test_raw_bash_false_in_heredoc_nameerrors(self):
        """Document the original bug: interpolating bash false is a Python NameError."""
        script = r"""
        had_queue_jam=false
        python3 - <<PY
had_queue_jam = ${had_queue_jam}
print(had_queue_jam)
PY
        """
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "NameError" in result.stderr
        assert "false" in result.stderr

    def test_health_script_interpolates_python_bool_literals(self):
        text = HEALTH_SCRIPT.read_text()
        assert 'py_bool() { [ "$1" = true ] && echo True || echo False; }' in text
        assert "had_queue_jam=${had_queue_jam_py}" in text
        assert "had_no_pipeline=${had_no_pipeline_py}" in text
        assert "had_recent_ingest=${had_recent_ingest_py}" in text
        assert "had_stale_ingest=${had_stale_ingest_py}" in text
        assert "had_queue_jam=${had_queue_jam}," not in text
        assert "remediator_enqueue_followup" in text
        assert "except ImportError:" in text
        assert "enqueue_classify_decision_failed" in text
        assert 'should_enqueue_classify="enqueue=error;reason=check_failed;action=error"' in text
        # Old bug: elif ran on bash flags even when Python decide failed (issue #224).
        assert (
            'elif [ "$had_no_pipeline" = true ] || [ "$had_stale_ingest" = true ]; then'
            not in text
        )
