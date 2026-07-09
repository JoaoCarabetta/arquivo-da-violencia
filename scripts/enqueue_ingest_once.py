#!/usr/bin/env python3
"""One-shot: enqueue ingest_cities_full_pipeline (no worker restart)."""
import asyncio

from app.tasks.worker import create_arq_pool


async def main() -> None:
    redis = await create_arq_pool()
    job = await redis.enqueue_job("ingest_cities_full_pipeline", None, "1h")
    print(f"enqueued job_id={job.job_id}")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
