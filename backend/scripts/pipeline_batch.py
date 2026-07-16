#!/usr/bin/env python3
"""Unified CLI for pipeline batch re-runs (reclassify, reextract, reenrich, …).

Usage (inside api container):

    python scripts/pipeline_batch.py reextract --since 2026-01-01 --dry-run
    python scripts/pipeline_batch.py reextract --ids 12,34 --execute --enqueue
    python scripts/pipeline_batch.py reenrich --city "Rio de Janeiro" --execute
    python scripts/pipeline_batch.py drain --stages enrich,geocode
    python scripts/pipeline_batch.py recollect --when 1d --full
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import batch_jobs


def _parse_since(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return [int(p) for p in parts]


def _add_mode(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Report only")
    mode.add_argument("--execute", action="store_true", help="Apply changes")


def _add_common_filters(parser: argparse.ArgumentParser, *, ids_help: str) -> None:
    parser.add_argument("--since", default=None, help="YYYY-MM-DD lower bound")
    parser.add_argument("--until", default=None, help="YYYY-MM-DD upper bound (inclusive)")
    parser.add_argument("--city", default=None, help="Filter by city (exact, case-insensitive)")
    parser.add_argument("--state", default=None, help="Filter by state (exact, case-insensitive)")
    parser.add_argument("--ids", default=None, help=ids_help)
    parser.add_argument("--limit", type=int, default=None, help="Max rows")
    parser.add_argument(
        "--enqueue",
        action="store_true",
        help="After execute, enqueue matching drain jobs",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON audit")


def _print_audit(audit: dict, *, json_mode: bool, label: str) -> None:
    if json_mode:
        print(json.dumps(audit, ensure_ascii=False, indent=2, default=str))
        return
    print(f"[{label}] {json.dumps(audit, ensure_ascii=False, default=str)}")


async def _maybe_enqueue_after(
    command: str,
    *,
    enqueue: bool,
    execute: bool,
) -> dict | None:
    if not enqueue or not execute:
        return None
    if command == "reextract":
        # Dedup first for any unlinked raws; enrich for still-linked uniques.
        return await batch_jobs.enqueue_drain(stages=["dedup", "enrich"])
    if command == "reenrich":
        return await batch_jobs.enqueue_drain(stages=["enrich"])
    if command == "regeocode":
        return await batch_jobs.enqueue_drain(stages=["geocode"])
    if command == "reclassify":
        return await batch_jobs.enqueue_drain(
            stages=["classify", "download", "extract", "dedup", "enrich"]
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline batch re-run toolkit (Docker/API container)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # reclassify
    p = sub.add_parser("reclassify", help="Requeue discarded false-negative sources")
    _add_mode(p)
    p.add_argument(
        "--signal",
        choices=("all", "death_keywords", "heuristic_true", "false_negative"),
        default="all",
    )
    p.add_argument("--since", default=None, help="Filter discarded by updated_at >= date")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--enqueue", action="store_true")
    p.add_argument("--json", action="store_true")

    # reextract
    p = sub.add_parser("reextract", help="In-place re-extract already-extracted sources")
    _add_mode(p)
    _add_common_filters(p, ids_help="Comma-separated source_google_news ids")
    p.add_argument("--concurrency", type=int, default=5)

    # reenrich
    p = sub.add_parser("reenrich", help="Flag unique_events for batch enrichment")
    _add_mode(p)
    _add_common_filters(p, ids_help="Comma-separated unique_event ids")

    # regeocode
    p = sub.add_parser("regeocode", help="Clear geocode so backlog can retry")
    _add_mode(p)
    _add_common_filters(p, ids_help="Comma-separated unique_event ids")

    # drain
    p = sub.add_parser("drain", help="Enqueue backlog drain jobs on namespaced queue")
    p.add_argument(
        "--stages",
        default=",".join(batch_jobs.ALL_DRAIN_STAGES),
        help="Comma-separated: classify,download,extract,dedup,enrich,geocode",
    )
    p.add_argument("--json", action="store_true")

    # recollect
    p = sub.add_parser("recollect", help="Enqueue city RSS ingest (when= window)")
    p.add_argument("--when", default="1d", help="Google News when window (e.g. 1h, 1d, 7d)")
    p.add_argument(
        "--full",
        action="store_true",
        help="Use ingest_cities_full_pipeline instead of ingest only",
    )
    p.add_argument("--json", action="store_true")

    return parser


async def _run(args: argparse.Namespace) -> dict:
    command = args.command

    if command == "drain":
        stages = [s.strip() for s in args.stages.split(",") if s.strip()]
        return await batch_jobs.enqueue_drain(stages=stages)

    if command == "recollect":
        return await batch_jobs.enqueue_recollect(
            when=args.when,
            full_pipeline=args.full,
        )

    dry_run = bool(args.dry_run)
    since = _parse_since(getattr(args, "since", None))
    until = _parse_since(getattr(args, "until", None))
    ids = _parse_ids(getattr(args, "ids", None))

    if command == "reclassify":
        audit = await batch_jobs.run_reclassify(
            dry_run=dry_run,
            limit=args.limit,
            since=since,
            signal=args.signal,
        )
    elif command == "reextract":
        audit = await batch_jobs.reextract_sources(
            dry_run=dry_run,
            limit=args.limit if args.limit is not None else 100,
            since=since,
            until=until,
            city=args.city,
            state=args.state,
            source_ids=ids,
            concurrency=args.concurrency,
        )
    elif command == "reenrich":
        audit = await batch_jobs.flag_reenrich(
            dry_run=dry_run,
            limit=args.limit if args.limit is not None else 500,
            since=since,
            until=until,
            city=args.city,
            state=args.state,
            unique_event_ids=ids,
        )
    elif command == "regeocode":
        audit = await batch_jobs.flag_regeocode(
            dry_run=dry_run,
            limit=args.limit if args.limit is not None else 500,
            since=since,
            until=until,
            city=args.city,
            state=args.state,
            unique_event_ids=ids,
        )
    else:
        raise SystemExit(f"Unknown command: {command}")

    enqueued = await _maybe_enqueue_after(
        command, enqueue=bool(getattr(args, "enqueue", False)), execute=not dry_run
    )
    if enqueued is not None:
        audit["enqueued"] = enqueued
    return audit


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    audit = asyncio.run(_run(args))
    label = "DRY-RUN" if getattr(args, "dry_run", False) else "EXECUTE"
    if args.command in ("drain", "recollect"):
        label = "ENQUEUE"
    _print_audit(audit, json_mode=bool(getattr(args, "json", False)), label=label)


if __name__ == "__main__":
    main()
