#!/usr/bin/env python3
"""Find near-duplicate unique_event groups in the database."""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dedup_scan import find_near_duplicate_groups


def write_csv(pair_rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "group_id", "id_a", "id_b", "similarity", "signal",
        "title_a", "title_b", "city", "event_date",
        "source_count_a", "source_count_b", "suggested_survivor_id",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pair_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Find near-duplicate unique_event groups.")
    parser.add_argument("--since", default="2026-07-04", help="Min event_date (YYYY-MM-DD)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "data"
        / "exploration_outputs"
        / "duplicate_groups_since_2026-07-04.csv",
    )
    args = parser.parse_args()

    pair_rows, group_summaries = asyncio.run(find_near_duplicate_groups(args.since))
    write_csv(pair_rows, args.out)

    print(f"Events scanned since {args.since}")
    print(f"Duplicate pairs found: {len(pair_rows)}")
    print(f"Duplicate groups: {len(group_summaries)}")
    print(f"Written to: {args.out}")

    for g in sorted(group_summaries, key=lambda x: -x["size"])[:15]:
        print(
            f"  group {g['group_id']}: ids={g['member_ids']} "
            f"survivor={g['survivor_id']} ({g['city']}, {g['event_date']})"
        )


if __name__ == "__main__":
    main()
