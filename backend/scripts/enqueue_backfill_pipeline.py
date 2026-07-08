#!/usr/bin/env python3
"""Enqueue pipeline jobs after backfill requeue."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings(host="redis", port=6379))
    await redis.enqueue_job("classify_pending_task", 300, 10)
    await redis.enqueue_job("download_classified_task", 200)
    await redis.enqueue_job("extract_ready_task", 100)
    await redis.enqueue_job("batch_enrich_task", 50)
    print("Pipeline jobs enqueued")


if __name__ == "__main__":
    asyncio.run(main())
