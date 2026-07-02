"""Build classification eval fixtures from a prod DB copy."""

from __future__ import annotations

import json
import random
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from eval.schemas import (
    CaseMetadata,
    ClassificationCase,
    ClassificationFixture,
    ClassificationInput,
    FixtureMeta,
    dump_fixture,
    load_fixture,
    update_fixture_counts,
)

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eval" / "classification.json"
)

DEATH_KEYWORDS = re.compile(
    r"\b(morto|morta|mortos|mortas|assassin|homicíd|homicid|executad|"
    r"corpo|feminicíd|feminicid|latrocín|latrocin|assassinat)\b",
    re.IGNORECASE,
)

POSITIVE_STATUSES = (
    "ready_for_download",
    "downloading",
    "ready_for_extraction",
    "extracting",
    "extracted",
)


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


def _heuristic_tags(headline: str, pool: str) -> list[str]:
    tags = [pool]
    lower = headline.lower()
    if any(w in lower for w in ("ferid", "balead", "sobreviv")):
        tags.append("injured_not_dead")
    if DEATH_KEYWORDS.search(headline):
        tags.append("death_keyword")
    if any(w in lower for w in ("operação", "operacao", "confronto", "tiroteio")):
        tags.append("ambiguous")
    if any(w in lower for w in ("prende", "apreend", "política", "politica")):
        tags.append("clear_false")
    if any(w in lower for w in ("morto", "morta", "assassin", "corpo")):
        tags.append("clear_true")
    return tags


def _fetch_rows(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    return conn.execute(query).fetchall()


def sample_classification_cases(conn: sqlite3.Connection, n: int) -> list[ClassificationCase]:
    negatives = _fetch_rows(
        conn,
        """
        SELECT id, headline
        FROM source_google_news
        WHERE status = 'discarded' AND is_violent_death = 0 AND headline IS NOT NULL
        """,
    )
    positives = _fetch_rows(
        conn,
        """
        SELECT id, headline
        FROM source_google_news
        WHERE status IN ({}) AND is_violent_death = 1 AND headline IS NOT NULL
        """.format(",".join(f"'{s}'" for s in POSITIVE_STATUSES)),
    )
    disagreements = _fetch_rows(
        conn,
        """
        SELECT id, headline
        FROM source_google_news
        WHERE status = 'discarded' AND headline IS NOT NULL
        """,
    )
    disagreement_rows = [r for r in disagreements if DEATH_KEYWORDS.search(r["headline"] or "")]

    per_pool = max(1, n // 3)
    pools = {
        "negative": [dict(r) for r in negatives],
        "positive": [dict(r) for r in positives],
        "disagreement": [dict(r) for r in disagreement_rows],
    }

    negative_groups: dict[str, list] = defaultdict(list)
    for row in pools["negative"]:
        negative_groups["negative"].append(row)

    positive_groups: dict[str, list] = defaultdict(list)
    for row in pools["positive"]:
        positive_groups["positive"].append(row)

    disagreement_groups: dict[str, list] = defaultdict(list)
    for row in pools["disagreement"]:
        disagreement_groups["disagreement"].append(row)

    selected: list[tuple[str, dict]] = (
        [("negative", row) for row in _round_robin(negative_groups, per_pool)]
        + [("positive", row) for row in _round_robin(positive_groups, per_pool)]
        + [("disagreement", row) for row in _round_robin(disagreement_groups, per_pool)]
    )
    random.shuffle(selected)
    selected = selected[:n]

    cases: list[ClassificationCase] = []
    for pool, row in selected:
        headline = row["headline"]
        source_id = row["id"]
        cases.append(
            ClassificationCase(
                id=f"cls-{source_id}",
                tags=_heuristic_tags(headline, pool),
                label_status="pending",
                input=ClassificationInput(headline=headline),
                expected=None,
                metadata=CaseMetadata(source_id=source_id, notes=""),
            )
        )
    return cases


def build_fixture(
    db_path: Path,
    n: int,
    seed: int,
    merge_into: Path | None = None,
) -> tuple[ClassificationFixture, int]:
    random.seed(seed)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        new_cases = sample_classification_cases(conn, n)
    finally:
        conn.close()

    existing_ids: set[str] = set()
    cases: list[ClassificationCase] = []
    meta = FixtureMeta(source_db=str(db_path), seed=seed)

    if merge_into and merge_into.exists():
        existing = load_fixture(json.loads(merge_into.read_text()))
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

    fixture = ClassificationFixture(meta=meta, cases=cases)
    update_fixture_counts(fixture)
    return fixture, added


def write_fixture(fixture: ClassificationFixture, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump_fixture(fixture), ensure_ascii=False, indent=2))
