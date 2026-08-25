"""Pipeline health check and remediation logic."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class InProgressJob:
    """Represents an ARQ in-progress job from Redis."""
    
    key: str
    job_name: str
    enqueued_at: Optional[datetime] = None
    
    @classmethod
    def from_redis_key(cls, key: str) -> "InProgressJob":
        """
        Parse an ARQ in-progress key to extract job information.
        
        Example keys:
        - arq:in-progress:abc123
        - arq:in-progress:cron:ingest_cities_hourly:1724594700
        """
        # Extract job name from the key
        parts = key.split(":")
        
        # For cron jobs: arq:in-progress:cron:JOB_NAME:TIMESTAMP
        if len(parts) >= 4 and parts[2] == "cron":
            job_name = parts[3]
            # Try to parse timestamp if present
            if len(parts) >= 5 and parts[4].isdigit():
                enqueued_at = datetime.fromtimestamp(int(parts[4]), tz=timezone.utc)
            else:
                enqueued_at = None
        else:
            # Non-cron job: arq:in-progress:JOB_ID
            job_name = "unknown"
            enqueued_at = None
        
        return cls(key=key, job_name=job_name, enqueued_at=enqueued_at)


@dataclass
class WorkerLogs:
    """Represents worker logs for progress analysis."""
    
    logs: str
    
    def has_multi_country_ingest_progress(self, lookback_minutes: int = 30) -> bool:
        """
        Check if logs show recent progress for multi-country ingestion.
        
        Progress indicators (actual patterns from ingestion.py):
        - Starting multi-country ingestion (N countries)
        - Starting PARALLEL city ingestion for N cities in COUNTRY
        - [CityName] Starting...
        - [CityName] Done: N entries, M new
        - INGESTION COMPLETE (COUNTRY)
        
        Args:
            lookback_minutes: How far back to look for progress (unused, for future timestamp parsing)
        
        Returns:
            True if there's evidence of progress in multi-country ingestion
        """
        # Look for multi-country ingest start
        if "Starting multi-country ingestion" in self.logs:
            return True
        
        # Look for parallel city ingestion start (per-country)
        if "Starting PARALLEL city ingestion" in self.logs:
            return True
        
        # Look for individual city progress
        # Format: [CityName] Done: 40 entries, 12 new
        if re.search(r"\[.+?\] Done: \d+ entries, \d+ new", self.logs):
            return True
        
        # Look for country-level completion
        # Format: INGESTION COMPLETE (BR)
        if re.search(r"INGESTION COMPLETE \(\w{2}\)", self.logs):
            return True
        
        return False


def should_treat_lock_as_stale(
    in_progress_jobs: list[InProgressJob],
    worker_logs: WorkerLogs,
    stale_threshold_minutes: int = 15,
) -> tuple[bool, str]:
    """
    Determine if ARQ in-progress locks should be treated as stale.
    
    Core logic: If the lock is held by a long-running ingest job (like
    ingest_all_countries or ingest_cities_hourly) and the worker is making
    progress, do NOT treat it as stale even if it exceeds the threshold.
    
    Args:
        in_progress_jobs: List of in-progress jobs from Redis
        worker_logs: Worker logs to check for progress
        stale_threshold_minutes: How long before a lock is considered stale (unused for ingest jobs)
    
    Returns:
        Tuple of (is_stale, reason)
    """
    if not in_progress_jobs:
        return False, "no_locks"
    
    # Check if any job is a long-running ingest
    ingest_job_names = {
        "ingest_cities_hourly",
        "ingest_cities_full_pipeline",
        "process_cities_backlog",
    }
    
    has_ingest_lock = False
    for job in in_progress_jobs:
        if job.job_name in ingest_job_names:
            has_ingest_lock = True
            break
    
    if not has_ingest_lock:
        # Not an ingest job, use normal stale detection
        return True, "non_ingest_lock_present"
    
    # It's an ingest job - check for progress
    if worker_logs.has_multi_country_ingest_progress():
        # Making progress, not stale
        return False, "ingest_lock_with_progress"
    
    # No progress detected, treat as stale
    return True, "ingest_lock_without_progress"


def should_enqueue_classify_during_remediation(
    had_queue_jam: bool,
    had_no_pipeline: bool,
    had_recent_ingest: bool,
    in_progress_jobs: list[InProgressJob],
    worker_logs: WorkerLogs,
) -> tuple[bool, str]:
    """
    Determine if classify_pending should be enqueued during remediation.
    
    Core logic: Do NOT enqueue classify if a multi-country ingest is still
    the active hourly task, even if there's a queue jam. The ingest needs
    to complete and log "MULTI-COUNTRY COMPLETE" before classify should run.
    
    Args:
        had_queue_jam: Whether a queue jam was detected
        had_no_pipeline: Whether no recent pipeline run was detected
        had_recent_ingest: Whether a recent ingest start was detected
        in_progress_jobs: List of in-progress jobs from Redis
        worker_logs: Worker logs to check for ingest state
    
    Returns:
        Tuple of (should_enqueue, reason)
    """
    # Check if ingest is currently active
    ingest_job_names = {
        "ingest_cities_hourly",
        "ingest_cities_full_pipeline",
    }
    
    active_ingest = False
    for job in in_progress_jobs:
        if job.job_name in ingest_job_names:
            active_ingest = True
            break
    
    # If there's an active ingest lock, don't enqueue classify
    # (even if queue appears jammed - it's just the long-running ingest)
    if active_ingest:
        # Check if it's making progress
        if worker_logs.has_multi_country_ingest_progress():
            return False, "active_ingest_with_progress"
        # No progress, but still has the lock - let other remediation handle it
        return False, "active_ingest_lock_present"
    
    # Original logic from the bash script:
    # Enqueue classify when queue is jammed OR when no pipeline but recent ingest
    if had_queue_jam:
        return True, "queue_jammed"
    
    if had_no_pipeline and had_recent_ingest:
        return True, "no_pipeline_with_recent_ingest"
    
    return False, "no_condition_met"
