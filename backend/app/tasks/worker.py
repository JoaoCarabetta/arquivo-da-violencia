"""ARQ worker configuration."""

import os
from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings

settings = get_settings()


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
    logger.info("ARQ Worker starting up...")
    logger.info(f"Cron enabled: {os.environ.get('ENABLE_CRON', 'false')}")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown handler."""
    from loguru import logger
    logger.info("ARQ Worker shutting down...")


def get_cron_jobs():
    """
    Get cron jobs based on environment configuration.
    
    Set ENABLE_CRON=true to enable scheduled jobs.
    """
    from app.tasks.pipeline import ingest_cities_task
    
    # Only enable cron if explicitly requested
    if os.environ.get("ENABLE_CRON", "false").lower() != "true":
        return []
    
    return [
        # Hourly city ingestion - runs at minute 5 of every hour
        # (offset from :00 to avoid peak API traffic)
        cron(
            ingest_cities_task,
            minute=5,  # Run at :05 every hour
            timeout=2000,  # 33 minutes timeout
            unique=True,  # Prevent duplicate runs
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
    
    # Retry settings
    max_tries = 3
    retry_delay = 60  # 1 minute between retries

