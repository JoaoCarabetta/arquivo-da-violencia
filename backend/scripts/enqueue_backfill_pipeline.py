#!/usr/bin/env python3
"""Enqueue pipeline jobs after backfill requeue (namespaced ARQ queue)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    from app.services.batch_jobs import enqueue_drain

    result = await enqueue_drain(
        stages=["classify", "download", "extract", "enrich"],
    )
    print(f"Pipeline jobs enqueued on {result['queue']}: {result['enqueued']}")


if __name__ == "__main__":
    asyncio.run(main())
