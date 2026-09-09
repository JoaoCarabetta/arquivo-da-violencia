#!/usr/bin/env python3
"""Relabel UniqueEvents that are Brasil but have non-BR geography (issue #234).

Targets known ids (17, 837, 1061, 8240, 8258) and the city denylist
(Tumbler Ridge, Joanesburgo, Paramaribo, Homs). Sets the correct ISO
country from city/state evidence, or nulls country so the row leaves
BR rankings. Does not delete UniqueEvents.

Usage (from backend/ or via docker compose exec api):

    # Report planned writes without committing:
    python scripts/remediate_mislabeled_brazil_cities.py --dry-run

    # Apply the fix:
    python scripts/remediate_mislabeled_brazil_cities.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.maintenance import remediate_mislabeled_brazil_cities


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Relabel UniqueEvents labeled Brasil that have non-BR geography "
            "(Tumbler Ridge, Joanesburgo, Paramaribo, Homs / known ids)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would change without writing.",
    )
    args = parser.parse_args()
    audit = await remediate_mislabeled_brazil_cities(dry_run=args.dry_run)
    print(json.dumps(audit, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
