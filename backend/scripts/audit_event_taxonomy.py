#!/usr/bin/env python3
"""Audit prod DB copy: map legacy homicide_type → (event_family, event_subtype)."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from pathlib import Path

from app.taxonomy import format_legacy_homicide_type, parse_legacy_homicide_type

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "violence-copy.db"
DEFAULT_OUT = REPO_ROOT / "data" / "exploration_outputs" / "taxonomy_migration.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit event taxonomy on a DB snapshot")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--table", choices=("unique_event", "raw_event"), default="unique_event")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT id, homicide_type, title FROM {args.table} ORDER BY id"
    ).fetchall()
    conn.close()

    pair_counts: Counter[tuple[str, str]] = Counter()
    legacy_counts: Counter[str] = Counter()
    out_rows: list[dict] = []

    for row in rows:
        legacy = row["homicide_type"]
        family, subtype = parse_legacy_homicide_type(legacy)
        pair_counts[(family, subtype)] += 1
        legacy_counts[legacy or "(null)"] += 1
        out_rows.append(
            {
                "id": row["id"],
                "legacy_homicide_type": legacy or "",
                "proposed_family": family,
                "proposed_subtype": subtype,
                "proposed_label": format_legacy_homicide_type(family, subtype),
                "title": (row["title"] or "")[:120],
                "rule": "legacy_map",
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Table: {args.table} ({len(rows)} rows)")
    print("\nLegacy homicide_type:")
    for k, n in legacy_counts.most_common():
        print(f"  {k}: {n}")

    print("\nProposed (event_family, event_subtype):")
    for (fam, sub), n in pair_counts.most_common():
        print(f"  ({fam}, {sub}): {n}")

    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
