#!/usr/bin/env python3
"""One-shot prod/staging cleanup: near-dup merge + reclassify discarded.

Run on staging first, verify, then repeat on production.

Usage (inside api container):

    python scripts/backfill_prod_cleanup.py --dry-run
    python scripts/backfill_prod_cleanup.py --execute --since 2026-01-01
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
from app.services.maintenance import (
    merge_exact_duplicate_unique_events,
    merge_near_duplicate_unique_events,
)


async def run_cleanup(
    *,
    dry_run: bool,
    since: str,
    since_date: date,
    reclassify_limit: int,
    skip_merge: bool,
    skip_reclassify: bool,
) -> dict:
    audit: dict = {"dry_run": dry_run, "since": since, "steps": {}}

    if not skip_merge:
        exact = await merge_exact_duplicate_unique_events(dry_run=dry_run)
        near = await merge_near_duplicate_unique_events(since=since, dry_run=dry_run)
        audit["steps"]["merge_exact"] = exact
        audit["steps"]["merge_near"] = near

    if not skip_reclassify:
        candidates = await find_discarded_reclassification_candidates(
            limit=reclassify_limit,
            since=since_date,
            signal="all",
        )
        reclassify = await requeue_discarded_sources(
            [row["id"] for row in candidates],
            dry_run=dry_run,
        )
        reclassify["candidate_count"] = len(candidates)
        reclassify["sample_headlines"] = [
            (row.get("headline") or "")[:100] for row in candidates[:10]
        ]
        audit["steps"]["reclassify"] = reclassify

    audit["pipeline_hint"] = (
        "After --execute, enqueue pipeline workers: "
        "classify_pending_task, download/extract batches, run_pending_enrichments."
    )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Near-dup merge + reclassify discarded sources (staging/prod backfill)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--since",
        default="2026-01-01",
        help="Min event_date for near-dup scan; reclassify filter uses same date",
    )
    parser.add_argument(
        "--reclassify-limit",
        type=int,
        default=500,
        help="Max discarded sources to requeue",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Skip near/exact duplicate merge step",
    )
    parser.add_argument(
        "--skip-reclassify",
        action="store_true",
        help="Skip discarded reclassification step",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    dry_run = not args.execute
    since_date = date.fromisoformat(args.since)
    audit = asyncio.run(
        run_cleanup(
            dry_run=dry_run,
            since=args.since,
            since_date=since_date,
            reclassify_limit=args.reclassify_limit,
            skip_merge=args.skip_merge,
            skip_reclassify=args.skip_reclassify,
        )
    )

    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return

    label = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"[{label}] prod cleanup since={args.since}")
    if "merge_exact" in audit["steps"]:
        me = audit["steps"]["merge_exact"]
        mn = audit["steps"]["merge_near"]
        print(
            f"[{label}] merge exact: groups={me.get('groups_found', 0)} "
            f"events={me.get('events_merged', 0)}"
        )
        print(
            f"[{label}] merge near: groups={mn.get('groups_found', 0)} "
            f"events={mn.get('events_merged', 0)}"
        )
    if "reclassify" in audit["steps"]:
        rc = audit["steps"]["reclassify"]
        print(
            f"[{label}] reclassify: candidates={rc.get('candidate_count', rc.get('requeued', 0))} "
            f"requeued={rc.get('requeued', 0)} "
            f"by_status={rc.get('by_target_status', {})}"
        )
    print(audit["pipeline_hint"])


if __name__ == "__main__":
    main()
