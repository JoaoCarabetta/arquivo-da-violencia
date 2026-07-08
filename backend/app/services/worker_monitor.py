"""
Worker health monitor.

Runs inside the API process (the always-on observer that is independent of the
worker) and periodically reads the ARQ worker's heartbeat key from Redis. If the
worker stops heartbeating it sends a Telegram alert once, and a recovery alert
when it comes back.

This exists because Redis connectivity says nothing about whether the worker
process - which also schedules the ingestion cron - is actually alive. A dead
worker silently stalls the whole pipeline.
"""

import asyncio

from loguru import logger

from app.metrics import (
    set_cron_enabled,
    set_heartbeat_misses,
    set_open_failure_issues,
    set_queue_depth,
    set_redis_connected,
    set_worker_alive,
)
from app.routers.pipeline import collect_pipeline_status
from app.services.github import get_github_creator
from app.services.pipeline_inventory_metrics import refresh_pipeline_inventory_metrics
from app.services.telegram import notify_worker_down, notify_worker_recovered

# How often to poll the heartbeat key.
CHECK_INTERVAL_SECONDS = 60

# How often to refresh DB-backed inventory and GitHub failure-issue gauges.
INVENTORY_POLL_INTERVAL_SECONDS = 300

# Consecutive missed heartbeats before declaring the worker down. Kept high
# enough to ride out a normal deploy (graceful worker shutdown can take ~120s)
# without firing a false alarm.
MISS_THRESHOLD = 5


def _apply_status_metrics(status: dict) -> bool:
    """Update Prometheus health gauges from a pipeline status dict."""
    redis_ok = status.get("redis") == "connected"
    set_redis_connected(redis_ok)
    set_worker_alive(bool(status.get("worker_alive")))
    set_cron_enabled(bool(status.get("cron_enabled")))
    set_queue_depth(int(status.get("queued_jobs", 0)))
    return redis_ok


async def monitor_worker_health(stop_event: asyncio.Event) -> None:
    """Poll the worker heartbeat until ``stop_event`` is set."""
    consecutive_misses = 0
    alerted_down = False
    github_poll_counter = 0

    logger.info(
        f"[WorkerMonitor] Started (interval={CHECK_INTERVAL_SECONDS}s, "
        f"threshold={MISS_THRESHOLD})"
    )

    await refresh_pipeline_inventory_metrics()

    while not stop_event.is_set():
        try:
            status = await collect_pipeline_status()
            redis_ok = _apply_status_metrics(status)
            alive = bool(status.get("worker_alive")) if redis_ok else False

            github_poll_counter += CHECK_INTERVAL_SECONDS
            if github_poll_counter >= INVENTORY_POLL_INTERVAL_SECONDS:
                github_poll_counter = 0
                open_issues = await get_github_creator().count_open_failure_issues()
                if open_issues is not None:
                    set_open_failure_issues(open_issues)
                await refresh_pipeline_inventory_metrics()

            if not redis_ok:
                logger.warning(
                    "[WorkerMonitor] Redis unavailable; skipping heartbeat check"
                )
            elif alive:
                if alerted_down:
                    seconds_down = consecutive_misses * CHECK_INTERVAL_SECONDS
                    logger.info("[WorkerMonitor] Worker heartbeat recovered")
                    await notify_worker_recovered(seconds_down)
                consecutive_misses = 0
                set_heartbeat_misses(0)
                alerted_down = False
            else:
                consecutive_misses += 1
                set_heartbeat_misses(consecutive_misses)
                logger.warning(
                    f"[WorkerMonitor] Missed heartbeat "
                    f"({consecutive_misses}/{MISS_THRESHOLD})"
                )
                if consecutive_misses >= MISS_THRESHOLD and not alerted_down:
                    seconds_silent = consecutive_misses * CHECK_INTERVAL_SECONDS
                    logger.error("[WorkerMonitor] Worker appears down - alerting")
                    await notify_worker_down(seconds_silent)
                    alerted_down = True
        except Exception as e:
            set_redis_connected(False)
            logger.error(f"[WorkerMonitor] Health check error: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    logger.info("[WorkerMonitor] Stopped")
