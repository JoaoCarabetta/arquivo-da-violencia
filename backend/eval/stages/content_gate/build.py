"""Build content-gate eval fixtures from a prod DB copy.

The prod DB (currently) only contains articles that PASSED the gate and were
extracted, so `build` only produces positive cases. Negatives (aggregate
statistics, foreign events, survivors, roundups) come from `generate-hard`.
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

from eval.schemas import CaseMetadata
from eval.schemas_content_gate import (
    ContentGateCase,
    ContentGateExpected,
    ContentGateFixture,
    ContentGateFixtureMeta,
    ContentGateInput,
    dump_content_gate_fixture,
    load_content_gate_fixture,
    update_content_gate_fixture_counts,
)

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "content_gate.json"
)


def sample_content_gate_cases(
    conn: sqlite3.Connection,
    n: int,
    *,
    with_labels: bool,
) -> list[ContentGateCase]:
    rows = conn.execute(
        """
        SELECT s.id AS source_id, s.headline, s.content, s.publisher_name
        FROM source_google_news s
        JOIN raw_event r ON r.source_google_news_id = s.id
        WHERE s.status = 'extracted'
          AND s.content IS NOT NULL
          AND length(s.content) > 500
          AND r.extraction_success = 1
        """
    ).fetchall()

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row["publisher_name"] or "unknown"].append(dict(row))

    pools = {k: v for k, v in groups.items()}
    for pool in pools.values():
        random.shuffle(pool)
    keys = list(pools.keys())
    random.shuffle(keys)

    selected: list[dict] = []
    while len(selected) < n and any(pools.values()):
        for key in keys:
            if pools[key]:
                selected.append(pools[key].pop())
                if len(selected) >= n:
                    break

    cases: list[ContentGateCase] = []
    for row in selected:
        if with_labels:
            expected = ContentGateExpected(is_violent_death=True, is_single_incident=True)
            label_status = "labeled"
        else:
            expected = None
            label_status = "pending"
        cases.append(
            ContentGateCase(
                id=f"cg-{row['source_id']}",
                tags=["db_positive", row["publisher_name"] or "unknown"],
                label_status=label_status,
                input=ContentGateInput(headline=row["headline"] or "", content=row["content"]),
                expected=expected,
                metadata=CaseMetadata(
                    source_id=row["source_id"],
                    notes="bootstrapped label: passed gate + extraction succeeded in prod",
                ),
            )
        )
    return cases


def build_fixture(
    db_path: Path,
    n: int,
    seed: int,
    *,
    with_labels: bool,
    merge_into: Path | None = None,
) -> tuple[ContentGateFixture, int]:
    random.seed(seed)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        new_cases = sample_content_gate_cases(conn, n, with_labels=with_labels)
    finally:
        conn.close()

    cases: list[ContentGateCase] = []
    existing_ids: set[str] = set()
    meta = ContentGateFixtureMeta(source_db=str(db_path), seed=seed)

    if merge_into and merge_into.exists():
        existing = load_content_gate_fixture(json.loads(merge_into.read_text()))
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

    fixture = ContentGateFixture(meta=meta, cases=cases)
    update_content_gate_fixture_counts(fixture)
    return fixture, added


def write_fixture(fixture: ContentGateFixture, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump_content_gate_fixture(fixture), ensure_ascii=False, indent=2))
