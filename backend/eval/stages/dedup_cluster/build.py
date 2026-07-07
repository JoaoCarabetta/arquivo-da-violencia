"""Build dedup-cluster eval fixtures from a prod DB copy.

Each case simulates a batch-dedup group: raw events from the same city and
date window, where ground-truth clusters are the prod unique_event links
(multi-source unique events form true clusters; others are singletons).

The prod DB contains duplicate unique events (same incident split across
rows), so unique-event groups that share victim names are merged into a
single expected cluster to avoid label noise.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from eval.schemas import CaseMetadata
from eval.schemas_dedup import (
    DedupClusterCase,
    DedupClusterExpected,
    DedupClusterFixture,
    DedupClusterFixtureMeta,
    DedupClusterInput,
    load_dedup_cluster_fixture,
    update_dedup_fixture_counts,
)
from difflib import SequenceMatcher

from eval.stages.dedup_match.build import _date_str, _norm, _raw_event_data, _victim_names

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "dedup_cluster_seed.json"
)

MAX_EVENTS_PER_CASE = 8


def _row_name_keys(row) -> set[str]:
    """Normalized victim-name keys for duplicate-group detection."""
    keys: set[str] = set()
    for name in _victim_names(row["extraction_data"]):
        norm = _norm(name)
        if norm:
            keys.add(norm)
            tokens = norm.split()
            if len(tokens) >= 2:
                keys.add(f"{tokens[0]} {tokens[-1]}")
    return keys


def _rows_look_like_same_event(row_a, row_b) -> bool:
    """Text-similarity check for duplicate rows the prod pipeline failed to merge."""
    title_a, title_b = _norm(row_a["title"]), _norm(row_b["title"])
    if title_a and title_b and SequenceMatcher(None, title_a, title_b).ratio() >= 0.7:
        return True
    desc_a = _norm(row_a["chronological_description"])[:300]
    desc_b = _norm(row_b["chronological_description"])[:300]
    if desc_a and desc_b and SequenceMatcher(None, desc_a, desc_b).ratio() >= 0.55:
        return True
    return False


def _merge_duplicate_groups(by_unique: dict[int, list], rows_by_index: dict[int, object]) -> list[list[int]]:
    """Merge unique-event groups whose raw events share victim names or
    describe the same incident (near-identical titles/descriptions).

    Returns the expected clusters (lists of 1-based indices).
    """
    group_ids = list(by_unique.keys())
    parent = {g: g for g in group_ids}

    def find(g):
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    group_keys = {
        g: set().union(*(_row_name_keys(rows_by_index[i]) for i in indices))
        for g, indices in by_unique.items()
    }
    for i, ga in enumerate(group_ids):
        for gb in group_ids[i + 1 :]:
            if group_keys[ga] & group_keys[gb]:
                union(ga, gb)
                continue
            if any(
                _rows_look_like_same_event(rows_by_index[ia], rows_by_index[ib])
                for ia in by_unique[ga]
                for ib in by_unique[gb]
            ):
                union(ga, gb)

    merged: dict[int, list[int]] = {}
    for g, indices in by_unique.items():
        merged.setdefault(find(g), []).extend(indices)
    return [sorted(indices) for indices in merged.values()]


def sample_dedup_cluster_cases(conn: sqlite3.Connection, n: int) -> list[DedupClusterCase]:
    seed_clusters = conn.execute(
        """
        SELECT ue.id AS unique_event_id, ue.city, ue.event_date,
               COUNT(r.id) AS n_raw
        FROM unique_event ue
        JOIN raw_event r ON r.unique_event_id = ue.id
        WHERE ue.source_count > 1
          AND ue.city IS NOT NULL
          AND ue.event_date IS NOT NULL
        GROUP BY ue.id
        HAVING n_raw >= 2 AND n_raw <= 4
        """
    ).fetchall()
    random.shuffle(seed_clusters)

    cases: list[DedupClusterCase] = []
    used_unique_ids: set[int] = set()

    for seed in seed_clusters:
        if len(cases) >= n:
            break
        if seed["unique_event_id"] in used_unique_ids:
            continue

        cluster_rows = conn.execute(
            """
            SELECT * FROM raw_event
            WHERE unique_event_id = ?
              AND city IS NOT NULL
            """,
            (seed["unique_event_id"],),
        ).fetchall()
        if len(cluster_rows) < 2:
            continue

        other_rows = conn.execute(
            """
            SELECT r.* FROM raw_event r
            JOIN unique_event ue ON ue.id = r.unique_event_id
            WHERE LOWER(r.city) = LOWER(?)
              AND r.unique_event_id != ?
              AND r.event_date IS NOT NULL
              AND ABS(julianday(r.event_date) - julianday(?)) <= 1
            LIMIT 6
            """,
            (seed["city"], seed["unique_event_id"], seed["event_date"]),
        ).fetchall()

        rows = list(cluster_rows) + list(other_rows)
        if len(rows) < 3:
            continue
        rows = rows[:MAX_EVENTS_PER_CASE]
        random.shuffle(rows)

        by_unique: dict[int, list[int]] = {}
        rows_by_index: dict[int, object] = {}
        events = []
        for i, row in enumerate(rows, start=1):
            events.append(_raw_event_data(row))
            by_unique.setdefault(row["unique_event_id"], []).append(i)
            rows_by_index[i] = row

        if len(by_unique) < 2:
            continue

        expected_clusters = _merge_duplicate_groups(by_unique, rows_by_index)
        if len(expected_clusters) < 2:
            continue

        has_names = any(_victim_names(row["extraction_data"]) for row in rows)
        used_unique_ids.update(by_unique.keys())

        cases.append(
            DedupClusterCase(
                id=f"dc-{seed['unique_event_id']}",
                tags=[
                    "with_names" if has_names else "no_names",
                    f"events_{len(events)}",
                    f"clusters_{len(expected_clusters)}",
                ],
                label_status="labeled",
                input=DedupClusterInput(events=events),
                expected=DedupClusterExpected(clusters=expected_clusters),
                metadata=CaseMetadata(
                    notes=f"city={seed['city']} date={_date_str(seed['event_date'])}; "
                    "bootstrapped from prod unique_event links",
                ),
            )
        )

    return cases


def build_fixture(
    db_path: Path,
    n: int,
    seed: int,
    *,
    merge_into: Path | None = None,
) -> tuple[DedupClusterFixture, int]:
    random.seed(seed)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        new_cases = sample_dedup_cluster_cases(conn, n)
    finally:
        conn.close()

    cases: list[DedupClusterCase] = []
    existing_ids: set[str] = set()
    meta = DedupClusterFixtureMeta(source_db=str(db_path), seed=seed)

    if merge_into and merge_into.exists():
        existing = load_dedup_cluster_fixture(json.loads(merge_into.read_text()))
        cases.extend(existing.cases)
        existing_ids = {c.id for c in existing.cases}
        meta = existing.meta
        meta.source_db = str(db_path)
        meta.seed = seed

    added = 0
    for case in new_cases:
        if case.id in existing_ids:
            continue
        cases.append(case)
        existing_ids.add(case.id)
        added += 1

    fixture = DedupClusterFixture(meta=meta, cases=cases)
    update_dedup_fixture_counts(fixture)
    return fixture, added


def write_fixture(fixture: DedupClusterFixture, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(fixture.model_dump(mode="json"), ensure_ascii=False, indent=2)
    )
