"""Build enrichment eval fixtures from a prod DB copy.

Samples enriched multi-source unique events. current_state approximates the
pre-enrichment state (base raw event fields), sources are the linked articles,
and expected is the post-enrichment unique_event row (bootstrapped labels).
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from eval.schemas import CaseMetadata
from eval.schemas_enrichment import (
    EnrichmentCase,
    EnrichmentFixture,
    EnrichmentFixtureMeta,
    EnrichmentInput,
    EnrichmentSource,
    dump_enrichment_fixture,
    load_enrichment_fixture,
    update_enrichment_fixture_counts,
)
from eval.stages.dedup_match.build import _date_str

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "enrichment.json"
)

# Mirrors enrich_unique_event: sources content fetched at 3000 chars.
SOURCE_CONTENT_CHARS = 3000


def sample_enrichment_cases(
    conn: sqlite3.Connection,
    n: int,
    *,
    with_labels: bool,
) -> list[EnrichmentCase]:
    unique_rows = conn.execute(
        """
        SELECT ue.* FROM unique_event ue
        WHERE ue.source_count > 1
          AND ue.last_enriched_at IS NOT NULL
          AND ue.city IS NOT NULL
          AND ue.event_date IS NOT NULL
        """
    ).fetchall()
    random.shuffle(unique_rows)

    cases: list[EnrichmentCase] = []
    for ue in unique_rows:
        if len(cases) >= n:
            break

        source_rows = conn.execute(
            """
            SELECT re.id AS raw_event_id, re.title AS raw_title,
                   re.event_date AS raw_event_date, re.city AS raw_city,
                   re.state AS raw_state, re.neighborhood AS raw_neighborhood,
                   re.victim_count AS raw_victim_count,
                   re.chronological_description AS raw_description,
                   sgn.content, sgn.headline, sgn.publisher_name, sgn.resolved_url
            FROM raw_event re
            LEFT JOIN source_google_news sgn ON re.source_google_news_id = sgn.id
            WHERE re.unique_event_id = ?
            ORDER BY re.id
            """,
            (ue["id"],),
        ).fetchall()

        usable = [r for r in source_rows if r["content"] and len(r["content"]) > 200]
        if len(usable) < 2:
            continue

        base = usable[0]
        current_state = {
            "title": base["raw_title"],
            "event_date": _date_str(base["raw_event_date"]),
            "city": base["raw_city"],
            "state": base["raw_state"],
            "neighborhood": base["raw_neighborhood"],
            "street": None,
            "victims_summary": None,
            "chronological_description": base["raw_description"],
        }

        sources = [
            EnrichmentSource(
                publisher=r["publisher_name"],
                headline=r["headline"],
                url=r["resolved_url"],
                content=(r["content"] or "")[:SOURCE_CONTENT_CHARS],
            )
            for r in usable
        ]

        if with_labels:
            expected = {
                "event_date": _date_str(ue["event_date"]),
                "city": ue["city"],
                "state": ue["state"],
                "neighborhood": ue["neighborhood"],
                "victim_count": ue["victim_count"],
                "victims_summary": ue["victims_summary"],
            }
            label_status = "labeled"
        else:
            expected = None
            label_status = "pending"

        cases.append(
            EnrichmentCase(
                id=f"en-{ue['id']}",
                tags=[f"sources_{len(sources)}"],
                label_status=label_status,
                input=EnrichmentInput(current_state=current_state, sources=sources),
                expected=expected,
                metadata=CaseMetadata(
                    notes=f"unique_event_id={ue['id']}; bootstrapped from prod enrichment "
                    f"({ue['enrichment_model'] or 'unknown model'})",
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
) -> tuple[EnrichmentFixture, int]:
    random.seed(seed)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        new_cases = sample_enrichment_cases(conn, n, with_labels=with_labels)
    finally:
        conn.close()

    cases: list[EnrichmentCase] = []
    existing_ids: set[str] = set()
    meta = EnrichmentFixtureMeta(source_db=str(db_path), seed=seed)

    if merge_into and merge_into.exists():
        existing = load_enrichment_fixture(json.loads(merge_into.read_text()))
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

    fixture = EnrichmentFixture(meta=meta, cases=cases)
    update_enrichment_fixture_counts(fixture)
    return fixture, added


def write_fixture(fixture: EnrichmentFixture, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump_enrichment_fixture(fixture), ensure_ascii=False, indent=2))
