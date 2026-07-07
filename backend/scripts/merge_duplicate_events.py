#!/usr/bin/env python3
"""Merge exact-duplicate unique_event groups in the database.

Groups events by normalized (title, city, date), keeps the row with the highest
source_count, re-links raw_events, and deletes duplicate unique_events.

Usage (from backend/ or via docker compose exec api):

    # Report planned merges without writing:
    python scripts/merge_duplicate_events.py --dry-run

    # Apply merges (destructive — back up the DB first):
    python scripts/merge_duplicate_events.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.maintenance import (
    merge_exact_duplicate_unique_events,
    merge_near_duplicate_unique_events,
    merge_unique_events_by_ids,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge exact duplicate unique_event groups (title+city+date)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Report duplicate groups without modifying the database",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Apply merges (destructive — back up the database first)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full audit JSON to stdout",
    )
    parser.add_argument(
        "--survivor",
        type=int,
        help="Survivor unique_event id for explicit merge (requires --losers)",
    )
    parser.add_argument(
        "--losers",
        type=int,
        nargs="+",
        help="Loser unique_event id(s) to merge into --survivor",
    )
    parser.add_argument(
        "--near-dupes",
        action="store_true",
        help="Merge fuzzy near-duplicate groups (requires --since)",
    )
    parser.add_argument(
        "--since",
        default="2026-07-04",
        help="Min event_date for --near-dupes scan (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    if args.survivor is not None:
        if not args.losers:
            parser.error("--survivor requires --losers")
        audit = asyncio.run(
            merge_unique_events_by_ids(
                args.survivor,
                args.losers,
                dry_run=not args.execute,
            )
        )
    elif args.near_dupes:
        audit = asyncio.run(
            merge_near_duplicate_unique_events(
                since=args.since,
                dry_run=not args.execute,
            )
        )
    else:
        audit = asyncio.run(merge_exact_duplicate_unique_events(dry_run=not args.execute))

    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        mode_label = "DRY-RUN" if audit.get("dry_run", not args.execute) else "EXECUTE"
        print(f"[{mode_label}] groups_found={audit.get('groups_found', 1)}")
        print(f"[{mode_label}] events_merged={audit.get('events_merged', 0)}")
        print(f"[{mode_label}] raw_events_relinked={audit.get('raw_events_relinked', 0)}")
        merges = audit.get("merges", [audit] if args.survivor else audit.get("merges", []))
        if args.survivor:
            merges = [audit]
        for merge in merges[:20]:
            print(
                f"  survivor={merge.get('survivor_id')} "
                f"losers={merge.get('loser_ids', [])} "
                f"raw_relinked={merge.get('raw_events_relinked', 0)} "
                f"title={merge.get('title', '')!r}"
            )
        if len(merges) > 20:
            print(f"  ... and {len(merges) - 20} more groups")


if __name__ == "__main__":
    main()
