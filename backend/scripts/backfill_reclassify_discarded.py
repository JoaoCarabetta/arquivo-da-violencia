#!/usr/bin/env python3
"""Requeue discarded sources that look like classification false negatives.

Usage (inside api container):

    python scripts/backfill_reclassify_discarded.py --dry-run
    python scripts/backfill_reclassify_discarded.py --execute --limit 200
    python scripts/backfill_reclassify_discarded.py --execute --signal heuristic_true
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.backfill import (
    find_discarded_reclassification_candidates,
    requeue_discarded_sources,
)


def _parse_since(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Requeue discarded Google News sources for reclassification."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Report candidates only")
    mode.add_argument("--execute", action="store_true", help="Apply requeue updates")
    parser.add_argument(
        "--signal",
        choices=("all", "death_keywords", "heuristic_true", "false_negative"),
        default="all",
        help="Candidate filter (default: all)",
    )
    parser.add_argument("--limit", type=int, default=500, help="Max sources to requeue")
    parser.add_argument(
        "--since",
        default=None,
        help="Only sources updated on/after YYYY-MM-DD",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON audit")
    args = parser.parse_args()

    since = _parse_since(args.since)
    candidates = asyncio.run(
        find_discarded_reclassification_candidates(
            limit=args.limit,
            since=since,
            signal=args.signal,
        )
    )
    source_ids = [row["id"] for row in candidates]
    audit = asyncio.run(
        requeue_discarded_sources(source_ids, dry_run=not args.execute)
    )
    audit["candidates"] = [
        {
            "id": row["id"],
            "headline": (row.get("headline") or "")[:120],
            "target_status": row["target_status"],
            "is_violent_death": row.get("is_violent_death"),
        }
        for row in candidates[:50]
    ]
    audit["candidate_count"] = len(candidates)

    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return

    label = "DRY-RUN" if not args.execute else "EXECUTE"
    print(f"[{label}] signal={args.signal} since={since or 'any'}")
    print(f"[{label}] candidates={audit['candidate_count']}")
    print(f"[{label}] requeued={audit['requeued']}")
    print(f"[{label}] by_target_status={audit.get('by_target_status', {})}")
    for item in audit.get("candidates", [])[:15]:
        print(
            f"  id={item['id']} -> {item['target_status']} "
            f"\"{item['headline']}\""
        )
    if audit["candidate_count"] > 15:
        print(f"  ... and {audit['candidate_count'] - 15} more")


if __name__ == "__main__":
    main()
