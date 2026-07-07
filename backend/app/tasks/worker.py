"""ARQ worker configuration."""

import asyncio
import os
import json
from datetime import datetime, timezone

from arq import cron
from arq.connections import RedisSettings
from arq.constants import default_queue_name, health_check_key_suffix

from app.config import get_settings

settings = get_settings()

# Redis key under which the worker records its health heartbeat.
# Must match arq's default (queue_name + suffix) since WorkerSettings does not
# override queue_name / health_check_key. The API reads this key to tell whether
# the worker process is actually alive (separate from Redis connectivity).
HEALTH_CHECK_KEY = default_queue_name + health_check_key_suffix

# Redis key the worker publishes its own config to on startup, so the API
# (which runs in a different container and may not share ENABLE_CRON) can report
# whether cron is actually enabled on the running worker.
# Namespaced by environment so staging/prod workers sharing Redis do not clash.
WORKER_INFO_KEY = f"arquivo:worker:info:{settings.environment}"


def is_cron_enabled() -> bool:
    """Whether scheduled (cron) jobs are enabled for this worker."""
    return os.environ.get("ENABLE_CRON", "false").lower() == "true"


def get_redis_settings() -> RedisSettings:
    """Get Redis settings from app config."""
    # Parse redis URL: redis://localhost:6379
    url = settings.redis_url
    if url.startswith("redis://"):
        url = url[8:]  # Remove redis://
    
    host, port = url.split(":")
    return RedisSettings(host=host, port=int(port))


async def startup(ctx: dict) -> None:
    """Worker startup handler."""
    from loguru import logger
    cron_enabled = is_cron_enabled()
    logger.info("ARQ Worker starting up...")
    logger.info(f"Cron enabled: {cron_enabled}")

    # Publish worker config to Redis so the API can report accurate status even
    # though it runs in a separate container without ENABLE_CRON set.
    redis = ctx.get("redis")
    if redis is not None:
        try:
            await redis.set(
                WORKER_INFO_KEY,
                json.dumps(
                    {
                        "cron_enabled": cron_enabled,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
        except Exception as e:  # pragma: no cover - best effort, non-fatal
            logger.warning(f"Failed to publish worker info to Redis: {e}")

    # Requeue any sources left stranded in a transient processing state by a
    # previous worker that crashed or errored mid-batch.
    try:
        from app.services.maintenance import recover_stuck_sources

        await recover_stuck_sources(older_than_minutes=5)
    except Exception as e:  # pragma: no cover - best effort, non-fatal
        logger.warning(f"Failed to recover stuck sources on startup: {e}")

    try:
        from app.metrics import push_loop

        ctx["metrics_task"] = asyncio.create_task(
            push_loop(settings.metrics_push_interval_seconds)
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to start metrics push loop: {e}")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown handler."""
    from loguru import logger
    logger.info("ARQ Worker shutting down...")

    metrics_task = ctx.get("metrics_task")
    if metrics_task is not None and not metrics_task.done():
        metrics_task.cancel()
        try:
            await metrics_task
        except (asyncio.CancelledError, Exception):  # pragma: no cover
            pass


def get_cron_jobs():
    """
    Get cron jobs based on environment configuration.
    
    Set ENABLE_CRON=true to enable scheduled jobs.
    """
    from app.tasks.pipeline import ingest_cities_hourly, process_cities_backlog

    # Only enable cron if explicitly requested
    if not is_cron_enabled():
        return []

    return [
        # Hourly ingest only — short job so :05 always fires even when backlog
        # processing from a prior hour is still running.
        cron(
            ingest_cities_hourly,
            minute=5,
            timeout=1800,
            unique=True,
        ),
        # Backlog drain every hour at :35 UTC (30 min after ingest at :05).
        # May exceed 1 hour; unique=True prevents overlap but does not block ingest.
        cron(
            process_cities_backlog,
            minute=35,
            timeout=7200,
            unique=True,
        ),
    ]


class WorkerSettings:
    """ARQ Worker settings."""
    
    # Redis connection
    redis_settings = get_redis_settings()
    
    # Task functions
    from app.tasks.pipeline import TASK_FUNCTIONS
    functions = TASK_FUNCTIONS
    
    # Startup/shutdown handlers
    on_startup = startup
    on_shutdown = shutdown
    
    # Cron jobs (scheduled tasks) - loaded dynamically
    cron_jobs = get_cron_jobs()
    
    # Worker settings
    max_jobs = 10
    job_timeout = 600  # 10 minutes default timeout (city ingestion can be slow)
    keep_result = 3600  # Keep results for 1 hour
    # Refresh the health-check key every 30s (default is 3600s) so the API can
    # detect a dead/crashed worker within ~30s instead of up to an hour.
    health_check_interval = 30
    
    # Retry settings
    max_tries = 3
    retry_delay = 60  # 1 minute between retries

