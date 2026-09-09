#!/usr/bin/env python3
"""Clamp Brazil UniqueEvent dates that sit after source publication (issue #228).

Re-checks UniqueEvents whose event_date is after the linked article's
published_at (or created_at / fetched_at when publish is missing). Applies the
same previous-year-or-null rule used at extract time.

Brazil-only by default (prod PIPELINE_ACTIVE_COUNTRIES=["BR"]).

Usage (from backend/ or via docker compose exec api):

    # Apply the fix (default):
    python scripts/remediate_future_event_dates.py

    # Report planned writes without committing:
    python scripts/remediate_future_event_dates.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.maintenance import remediate_future_event_dates


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clamp UniqueEvent dates that are after source publication."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would change without writing.",
    )
    parser.add_argument(
        "--country",
        default="BR",
        help="ISO country to remediate (default: BR).",
    )
    args = parser.parse_args()
    audit = await remediate_future_event_dates(
        dry_run=args.dry_run,
        country=args.country,
    )
    print(json.dumps(audit, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
