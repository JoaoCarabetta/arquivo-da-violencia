"""Build extraction eval fixtures from a prod DB copy."""

from __future__ import annotations

import json
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

from eval.schemas import CaseMetadata
from eval.schemas_extraction import (
    ExtractionCase,
    ExtractionFixture,
    ExtractionFixtureMeta,
    ExtractionInput,
    ExtractionMetadata,
    dump_extraction_fixture,
    load_extraction_fixture,
    update_extraction_fixture_counts,
)

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "extraction.json"
)


def _length_bucket(n: int) -> str:
    if n < 2000:
        return "short"
    if n <= 10000:
        return "medium"
    return "long"


def _round_robin(groups: dict[str, list], total: int) -> list:
    selected: list = []
    pools = {k: list(v) for k, v in groups.items()}
    for pool in pools.values():
        random.shuffle(pool)
    keys = list(pools.keys())
    random.shuffle(keys)
    while len(selected) < total and any(pools.values()):
        for key in keys:
            if not pools[key]:
                continue
            selected.append(pools[key].pop())
            if len(selected) >= total:
                break
    return selected


def _project_expected(extraction_data: dict) -> dict:
    """Keep only fields commonly scored in eval fixtures."""
    return {
        "date_time": {
            "date": _deep_get(extraction_data, "date_time", "date"),
            "date_verification": {
                "has_explicit_date": _deep_get(
                    extraction_data, "date_time", "date_verification", "has_explicit_date"
                ),
            },
        },
        "location_info": {
            "city": _deep_get(extraction_data, "location_info", "city"),
            "state": _deep_get(extraction_data, "location_info", "state"),
            "neighborhood": _deep_get(extraction_data, "location_info", "neighborhood"),
        },
        "victims": {
            "number_of_victims": _deep_get(extraction_data, "victims", "number_of_victims"),
        },
        "event_family": _deep_get(extraction_data, "event_family"),
        "event_subtype": _deep_get(extraction_data, "event_subtype"),
        "homicide_dynamic": {
            "method": _deep_get(extraction_data, "homicide_dynamic", "method"),
        },
    }


def _deep_get(data: dict, *keys):
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def sample_extraction_cases(
    conn: sqlite3.Connection,
    n: int,
    *,
    with_labels: bool,
) -> list[ExtractionCase]:
    rows = conn.execute(
        """
        SELECT
            s.id AS source_id,
            s.headline,
            s.content,
            s.published_at,
            s.publisher_name,
            s.resolved_url,
            r.id AS raw_event_id,
            r.extraction_data
        FROM source_google_news s
        JOIN raw_event r ON r.source_google_news_id = s.id
        WHERE s.status = 'extracted'
          AND s.content IS NOT NULL
          AND s.content != ''
          AND r.extraction_success = 1
          AND r.extraction_data IS NOT NULL
        """
    ).fetchall()

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        content = row["content"] or ""
        bucket = _length_bucket(len(content))
        publisher = row["publisher_name"] or "unknown"
        key = f"{bucket}|{publisher}"
        groups[key].append(dict(row))

    selected = _round_robin(groups, n)
    cases: list[ExtractionCase] = []
    for row in selected:
        raw_data = row["extraction_data"]
        extraction_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        if with_labels:
            expected = _project_expected(extraction_data)
            label_status = "labeled"
        else:
            expected = None
            label_status = "pending"

        bucket = _length_bucket(len(row["content"] or ""))
        cases.append(
            ExtractionCase(
                id=f"ext-{row['raw_event_id']}",
                tags=[bucket, row["publisher_name"] or "unknown"],
                label_status=label_status,
                input=ExtractionInput(
                    content=row["content"],
                    metadata=ExtractionMetadata(
                        headline=row["headline"],
                        published_at=row["published_at"],
                        publisher=row["publisher_name"],
                        url=row["resolved_url"],
                    ),
                ),
                expected=expected,
                metadata=CaseMetadata(
                    source_id=row["source_id"],
                    notes=f"raw_event_id={row['raw_event_id']}",
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
) -> tuple[ExtractionFixture, int]:
    random.seed(seed)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        new_cases = sample_extraction_cases(conn, n, with_labels=with_labels)
    finally:
        conn.close()

    cases: list[ExtractionCase] = []
    existing_ids: set[str] = set()
    meta = ExtractionFixtureMeta(source_db=str(db_path), seed=seed)

    if merge_into and merge_into.exists():
        existing = load_extraction_fixture(json.loads(merge_into.read_text()))
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

    fixture = ExtractionFixture(meta=meta, cases=cases)
    update_extraction_fixture_counts(fixture)
    return fixture, added


def write_fixture(fixture: ExtractionFixture, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump_extraction_fixture(fixture), ensure_ascii=False, indent=2))
