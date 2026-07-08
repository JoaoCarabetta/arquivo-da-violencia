"""Prometheus metrics for the pipeline."""

from __future__ import annotations

import asyncio
import time

import httpx
from loguru import logger
from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.config import get_settings

# API /metrics exposes health gauges (and HTTP metrics via instrumentator).
REGISTRY: CollectorRegistry = DEFAULT_REGISTRY

# Worker :9091/metrics exposes only task/attempt counters and histograms.
WORKER_REGISTRY = CollectorRegistry()

pipeline_task_total = Counter(
    "pipeline_task_total",
    "Total ARQ tasks executed, by task name and outcome.",
    labelnames=["task", "outcome"],
    registry=WORKER_REGISTRY,
)

pipeline_task_duration_seconds = Histogram(
    "pipeline_task_duration_seconds",
    "Wall-clock duration of ARQ tasks, by task name and outcome.",
    labelnames=["task", "outcome"],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
    registry=WORKER_REGISTRY,
)

pipeline_attempts_total = Counter(
    "pipeline_attempts_total",
    "Total download/extraction attempts recorded, by stage/outcome/failure_reason.",
    labelnames=["stage", "outcome", "failure_reason"],
    registry=WORKER_REGISTRY,
)

pipeline_attempt_duration_seconds = Histogram(
    "pipeline_attempt_duration_seconds",
    "Duration of individual download/extraction attempts, by stage/outcome.",
    labelnames=["stage", "outcome"],
    buckets=(0.5, 1, 2.5, 5, 10, 20, 30, 60, 120),
    registry=WORKER_REGISTRY,
)

pipeline_attempt_content_length_bytes = Histogram(
    "pipeline_attempt_content_length_bytes",
    "Content length (bytes) of downloaded article text, by stage.",
    labelnames=["stage"],
    buckets=(512, 2048, 8192, 32768, 131072, 524288, 2097152),
    registry=WORKER_REGISTRY,
)

pipeline_queue_depth = Gauge(
    "pipeline_queue_depth",
    "Number of jobs waiting in the ARQ queue.",
    registry=REGISTRY,
)

pipeline_worker_alive = Gauge(
    "pipeline_worker_alive",
    "1 if the ARQ worker heartbeat key is present in Redis, else 0.",
    registry=REGISTRY,
)

pipeline_cron_enabled = Gauge(
    "pipeline_cron_enabled",
    "1 if the worker has cron scheduling enabled, else 0.",
    registry=REGISTRY,
)

pipeline_worker_heartbeat_misses = Gauge(
    "pipeline_worker_heartbeat_misses",
    "Consecutive heartbeat misses observed by the API-side worker monitor.",
    registry=REGISTRY,
)

pipeline_redis_connected = Gauge(
    "pipeline_redis_connected",
    "1 if Redis is reachable from this process, else 0.",
    registry=REGISTRY,
)

pipeline_open_failure_issues = Gauge(
    "pipeline_open_failure_issues",
    "Number of open GitHub issues labeled pipeline-failure.",
    registry=REGISTRY,
)

pipeline_inventory_total = Gauge(
    "pipeline_inventory_total",
    "Total Google News sources in the database.",
    registry=REGISTRY,
)

pipeline_inventory_violent_death = Gauge(
    "pipeline_inventory_violent_death",
    "Sources classified as violent death (any status).",
    registry=REGISTRY,
)

pipeline_inventory_raw_events = Gauge(
    "pipeline_inventory_raw_events",
    "Total extracted raw events.",
    registry=REGISTRY,
)

pipeline_inventory_unique_events = Gauge(
    "pipeline_inventory_unique_events",
    "Total deduplicated unique events.",
    registry=REGISTRY,
)

pipeline_inventory_sources = Gauge(
    "pipeline_inventory_sources",
    "Google News sources currently in each pipeline status.",
    labelnames=["status"],
    registry=REGISTRY,
)

pipeline_stuck_sources = Gauge(
    "pipeline_stuck_sources",
    "Sources stuck in a transient status longer than the stuck threshold.",
    labelnames=["status"],
    registry=REGISTRY,
)

pipeline_attempt_failures_24h = Gauge(
    "pipeline_attempt_failures_24h",
    "Failed download/extraction attempts in the last 24 hours, by stage and reason.",
    labelnames=["stage", "failure_reason"],
    registry=REGISTRY,
)

pipeline_cron_last_success_timestamp = Gauge(
    "pipeline_cron_last_success_timestamp",
    "Unix timestamp of the last successful cron run, by cron name.",
    labelnames=["cron"],
    registry=WORKER_REGISTRY,
)

pipeline_cron_runs_total = Counter(
    "pipeline_cron_runs_total",
    "Total cron executions, by cron name and outcome.",
    labelnames=["cron", "outcome"],
    registry=WORKER_REGISTRY,
)

pipeline_failure_issues_created_total = Counter(
    "pipeline_failure_issues_created_total",
    "Total new GitHub pipeline-failure issues created, by task.",
    labelnames=["task"],
    registry=WORKER_REGISTRY,
)

pipeline_failure_issue_recurrences_total = Counter(
    "pipeline_failure_issue_recurrences_total",
    "Total recurrence comments added to existing pipeline-failure issues.",
    labelnames=["task"],
    registry=WORKER_REGISTRY,
)

CRON_TASKS = frozenset({"ingest_cities_hourly", "process_cities_backlog"})

_STUCK_STATUSES = ("classifying", "downloading", "extracting")
_seen_failure_labels: set[tuple[str, str]] = set()
_seen_inventory_statuses: set[str] = set()


def set_pipeline_inventory_metrics(
    *,
    status_counts: dict[str, int],
    stuck_counts: dict[str, int],
    failure_counts: dict[tuple[str, str], int],
    sources_total: int,
    violent_death: int,
    raw_events_total: int,
    unique_events_total: int,
) -> None:
    try:
        pipeline_inventory_total.set(sources_total)
        pipeline_inventory_violent_death.set(violent_death)
        pipeline_inventory_raw_events.set(raw_events_total)
        pipeline_inventory_unique_events.set(unique_events_total)

        current_statuses: set[str] = set()
        for status, count in status_counts.items():
            pipeline_inventory_sources.labels(status=status).set(count)
            current_statuses.add(status)
        for status in _seen_inventory_statuses - current_statuses:
            pipeline_inventory_sources.labels(status=status).set(0)
        _seen_inventory_statuses.clear()
        _seen_inventory_statuses.update(current_statuses)

        for status in _STUCK_STATUSES:
            pipeline_stuck_sources.labels(status=status).set(stuck_counts.get(status, 0))

        current_failures: set[tuple[str, str]] = set()
        for (stage, reason), count in failure_counts.items():
            pipeline_attempt_failures_24h.labels(
                stage=stage, failure_reason=reason
            ).set(count)
            current_failures.add((stage, reason))
        for stage, reason in _seen_failure_labels - current_failures:
            pipeline_attempt_failures_24h.labels(
                stage=stage, failure_reason=reason
            ).set(0)
        _seen_failure_labels.clear()
        _seen_failure_labels.update(current_failures)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_pipeline_inventory_metrics failed: {e}")


def generate_worker_metrics() -> bytes:
    """Prometheus exposition format for the worker metrics HTTP server."""
    return generate_latest(WORKER_REGISTRY)


def record_task_outcome(task_name: str, outcome: str, duration_seconds: float) -> None:
    try:
        pipeline_task_total.labels(task=task_name, outcome=outcome).inc()
        pipeline_task_duration_seconds.labels(task=task_name, outcome=outcome).observe(
            duration_seconds
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] record_task_outcome failed: {e}")


def record_attempt_metrics(
    *,
    stage: str,
    outcome: str,
    failure_reason: str | None = None,
    duration_ms: int | None = None,
    content_length: int | None = None,
) -> None:
    try:
        reason = failure_reason or "none"
        pipeline_attempts_total.labels(
            stage=stage, outcome=outcome, failure_reason=reason
        ).inc()
        if duration_ms is not None:
            pipeline_attempt_duration_seconds.labels(stage=stage, outcome=outcome).observe(
                duration_ms / 1000
            )
        if content_length is not None:
            pipeline_attempt_content_length_bytes.labels(stage=stage).observe(content_length)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] record_attempt_metrics failed: {e}")


def set_worker_alive(alive: bool) -> None:
    try:
        pipeline_worker_alive.set(1 if alive else 0)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_worker_alive failed: {e}")


def set_heartbeat_misses(misses: int) -> None:
    try:
        pipeline_worker_heartbeat_misses.set(misses)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_heartbeat_misses failed: {e}")


def set_queue_depth(depth: int) -> None:
    try:
        pipeline_queue_depth.set(depth)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_queue_depth failed: {e}")


def set_cron_enabled(enabled: bool) -> None:
    try:
        pipeline_cron_enabled.set(1 if enabled else 0)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_cron_enabled failed: {e}")


def set_redis_connected(connected: bool) -> None:
    try:
        pipeline_redis_connected.set(1 if connected else 0)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_redis_connected failed: {e}")


def set_open_failure_issues(count: int) -> None:
    try:
        pipeline_open_failure_issues.set(count)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] set_open_failure_issues failed: {e}")


def record_cron_outcome(cron_name: str, outcome: str) -> None:
    try:
        pipeline_cron_runs_total.labels(cron=cron_name, outcome=outcome).inc()
        if outcome == "success":
            pipeline_cron_last_success_timestamp.labels(cron=cron_name).set(time.time())
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] record_cron_outcome failed: {e}")


def record_failure_issue_created(task_name: str) -> None:
    try:
        pipeline_failure_issues_created_total.labels(task=task_name).inc()
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] record_failure_issue_created failed: {e}")


def record_failure_issue_recurrence(task_name: str) -> None:
    try:
        pipeline_failure_issue_recurrences_total.labels(task=task_name).inc()
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] record_failure_issue_recurrence failed: {e}")


def _is_push_configured() -> bool:
    s = get_settings()
    return bool(
        s.grafana_cloud_prom_url
        and s.grafana_cloud_prom_user
        and s.grafana_cloud_prom_key
        and s.metrics_enabled
    )


async def push_to_grafana_cloud() -> bool:
    if not _is_push_configured():
        return False

    s = get_settings()
    try:
        body = generate_latest(WORKER_REGISTRY)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                s.grafana_cloud_prom_url,
                content=body,
                headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
                auth=(s.grafana_cloud_prom_user, s.grafana_cloud_prom_key),
            )
        if resp.status_code >= 400:
            logger.warning(
                f"[metrics] Grafana Cloud push failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
            return False
        return True
    except Exception as e:  # pragma: no cover
        logger.warning(f"[metrics] push_to_grafana_cloud error: {e}")
        return False


async def push_loop(interval_seconds: int) -> None:
    if not _is_push_configured():
        logger.info("[metrics] Grafana Cloud push disabled (no URL/user/key)")
        return
    logger.info(f"[metrics] Pushing to Grafana Cloud every {interval_seconds}s")
    while True:
        try:
            await push_to_grafana_cloud()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover
            logger.warning(f"[metrics] push_loop error: {e}")
        await asyncio.sleep(interval_seconds)
