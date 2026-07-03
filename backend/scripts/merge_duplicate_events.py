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

from app.services.maintenance import merge_exact_duplicate_unique_events


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
    args = parser.parse_args()

    audit = asyncio.run(merge_exact_duplicate_unique_events(dry_run=not args.execute))

    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        mode_label = "DRY-RUN" if audit["dry_run"] else "EXECUTE"
        print(f"[{mode_label}] groups_found={audit['groups_found']}")
        print(f"[{mode_label}] events_merged={audit['events_merged']}")
        print(f"[{mode_label}] raw_events_relinked={audit['raw_events_relinked']}")
        for merge in audit["merges"][:20]:
            print(
                f"  survivor={merge['survivor_id']} "
                f"losers={merge['loser_ids']} "
                f"raw_relinked={merge['raw_events_relinked']} "
                f"title={merge['title']!r}"
            )
        if len(audit["merges"]) > 20:
            print(f"  ... and {len(audit['merges']) - 20} more groups")


if __name__ == "__main__":
    main()
