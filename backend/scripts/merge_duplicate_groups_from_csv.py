#!/usr/bin/env python3
"""Apply merges from duplicate_groups CSV on production.

Usage on prod (after CSV is present):
    python scripts/merge_duplicate_groups_from_csv.py --csv /tmp/dupes.csv --dry-run
    python scripts/merge_duplicate_groups_from_csv.py --csv /tmp/dupes.csv --execute
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.maintenance import merge_unique_events_by_ids, pick_survivor_id


def _groups_from_csv(path: Path) -> list[dict]:
    pairs = list(csv.DictReader(path.open(encoding="utf-8")))
    uf: dict[int, int] = {}

    def find(x: int) -> int:
        uf.setdefault(x, x)
        while uf[x] != x:
            uf[x] = uf[uf[x]]
            x = uf[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            uf[rb] = ra

    members_by_id: dict[int, dict] = {}
    for row in pairs:
        id_a, id_b = int(row["id_a"]), int(row["id_b"])
        union(id_a, id_b)
        sc_a = int(row.get("source_count_a") or 1)
        sc_b = int(row.get("source_count_b") or 1)
        members_by_id[id_a] = {"id": id_a, "source_count": sc_a}
        members_by_id[id_b] = {"id": id_b, "source_count": sc_b}

    grouped: dict[int, list[dict]] = defaultdict(list)
    for mid, member in members_by_id.items():
        grouped[find(mid)].append(member)

    result = []
    for _root, members in grouped.items():
        if len(members) < 2:
            continue
        survivor_id = pick_survivor_id(members)
        loser_ids = [m["id"] for m in members if m["id"] != survivor_id]
        result.append({"survivor_id": survivor_id, "loser_ids": loser_ids})
    return result


async def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()

    groups = _groups_from_csv(args.csv)
    total_merged = 0
    total_relinked = 0
    for group in groups:
        audit = await merge_unique_events_by_ids(
            group["survivor_id"],
            group["loser_ids"],
            dry_run=not args.execute,
        )
        total_merged += audit.get("events_merged", 0)
        total_relinked += audit.get("raw_events_relinked", 0)
        print(
            f"survivor={audit['survivor_id']} losers={audit['loser_ids']} "
            f"raw_relinked={audit['raw_events_relinked']}"
        )
    print(f"groups={len(groups)} events_merged={total_merged} raw_relinked={total_relinked}")


if __name__ == "__main__":
    asyncio.run(main())
