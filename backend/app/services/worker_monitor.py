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

from arq import create_pool
from loguru import logger

from app.tasks.worker import get_redis_settings, HEALTH_CHECK_KEY
from app.services.telegram import notify_worker_down, notify_worker_recovered

# How often to poll the heartbeat key.
CHECK_INTERVAL_SECONDS = 60

# Consecutive missed heartbeats before declaring the worker down. Kept high
# enough to ride out a normal deploy (graceful worker shutdown can take ~120s)
# without firing a false alarm.
MISS_THRESHOLD = 5


async def monitor_worker_health(stop_event: asyncio.Event) -> None:
    """Poll the worker heartbeat until ``stop_event`` is set."""
    consecutive_misses = 0
    alerted_down = False
    pool = None

    logger.info(
        f"[WorkerMonitor] Started (interval={CHECK_INTERVAL_SECONDS}s, "
        f"threshold={MISS_THRESHOLD})"
    )

    while not stop_event.is_set():
        try:
            if pool is None:
                pool = await create_pool(get_redis_settings())

            alive = await pool.get(HEALTH_CHECK_KEY) is not None

            if alive:
                if alerted_down:
                    seconds_down = consecutive_misses * CHECK_INTERVAL_SECONDS
                    logger.info("[WorkerMonitor] Worker heartbeat recovered")
                    await notify_worker_recovered(seconds_down)
                consecutive_misses = 0
                alerted_down = False
            else:
                consecutive_misses += 1
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
            # Redis errors etc. - don't treat as "worker down" (that's a
            # different failure mode). Drop the pool so we reconnect cleanly.
            logger.error(f"[WorkerMonitor] Health check error: {e}")
            if pool is not None:
                try:
                    await pool.close()
                except Exception:
                    pass
                pool = None

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass

    logger.info("[WorkerMonitor] Stopped")
