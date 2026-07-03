"""Build dedup-match eval fixtures from a prod DB copy.

Positives: raw events that were LLM-matched to a unique event in prod
(candidates = true unique event + same-city/±3d distractors).
Negatives: the same raw events with the true unique event REMOVED from the
candidate list (only distractors remain), so the correct answer is "no match".

IMPORTANT: the prod DB contains duplicate unique events (same incident split
across several rows), so distractors that mention the raw event's victims or
have near-identical titles are filtered out - otherwise the "wrong" candidate
would actually be a correct match and the label would be noise.
"""

from __future__ import annotations

import json
import random
import sqlite3
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from eval.schemas import CaseMetadata
from eval.schemas_dedup import (
    DedupMatchCase,
    DedupMatchExpected,
    DedupMatchFixture,
    DedupMatchFixtureMeta,
    DedupMatchInput,
    RawEventData,
    UniqueEventData,
    load_dedup_match_fixture,
    update_dedup_fixture_counts,
)

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "dedup_match.json"
)


def _date_str(value) -> str | None:
    if not value:
        return None
    return str(value)[:10]


def _victim_names(extraction_data_json) -> list[str]:
    if not extraction_data_json:
        return []
    try:
        data = json.loads(extraction_data_json) if isinstance(extraction_data_json, str) else extraction_data_json
    except (json.JSONDecodeError, TypeError):
        return []
    victims = (data or {}).get("victims", {}) or {}
    names = []
    for victim in victims.get("identifiable_victims", []) or []:
        name = (victim or {}).get("name")
        if name and len(name.strip()) > 3:
            names.append(name.strip())
    return names


def _raw_event_data(row) -> RawEventData:
    return RawEventData(
        id=row["id"],
        title=row["title"],
        event_date=_date_str(row["event_date"]),
        city=row["city"],
        state=row["state"],
        neighborhood=row["neighborhood"],
        homicide_type=row["homicide_type"],
        chronological_description=row["chronological_description"],
        victim_names=_victim_names(row["extraction_data"]),
    )


def _unique_event_data(row) -> UniqueEventData:
    return UniqueEventData(
        id=row["id"],
        title=row["title"],
        event_date=_date_str(row["event_date"]),
        city=row["city"],
        state=row["state"],
        neighborhood=row["neighborhood"],
        homicide_type=row["homicide_type"],
        chronological_description=row["chronological_description"],
        victims_summary=row["victims_summary"],
        victim_count=row["victim_count"],
        source_count=row["source_count"] or 1,
    )


def _norm(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text.lower().strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split())


def _looks_like_same_event(raw_row, candidate_row) -> bool:
    """Heuristic filter for distractors that are probably the SAME incident.

    The prod DB has duplicate unique events, so a same-city/same-date
    candidate may actually describe the raw event's incident. Reject
    candidates sharing victim names, near-identical titles, or highly
    similar descriptions.
    """
    raw_names = {_norm(n) for n in _victim_names(raw_row["extraction_data"])}
    raw_text = _norm(
        " ".join(str(raw_row[k] or "") for k in ("title", "chronological_description"))
    )
    candidate_text = _norm(
        " ".join(
            str(candidate_row[k] or "")
            for k in ("victims_summary", "title", "chronological_description")
        )
    )
    for name in raw_names:
        if name and name in candidate_text:
            return True
        tokens = name.split()
        # Any consecutive token pair of the name (e.g. "tony viegas") counts,
        # as does first+last token co-occurrence.
        for a, b in zip(tokens, tokens[1:]):
            if f"{a} {b}" in candidate_text:
                return True
        if len(tokens) >= 2 and tokens[0] in candidate_text and tokens[-1] in candidate_text:
            return True

    # Reverse: candidate victim name appearing in the raw event text.
    cand_summary = _norm(candidate_row["victims_summary"])
    if cand_summary:
        cand_name = cand_summary.split(",")[0].strip()
        cand_tokens = cand_name.split()
        if len(cand_tokens) >= 2:
            for a, b in zip(cand_tokens, cand_tokens[1:]):
                if f"{a} {b}" in raw_text:
                    return True

    raw_title = _norm(raw_row["title"])
    cand_title = _norm(candidate_row["title"])
    if raw_title and cand_title:
        if raw_title in cand_title or cand_title in raw_title:
            return True
        if SequenceMatcher(None, raw_title, cand_title).ratio() >= 0.7:
            return True

    raw_desc = _norm(raw_row["chronological_description"])[:300]
    cand_desc = _norm(candidate_row["chronological_description"])[:300]
    if raw_desc and cand_desc and SequenceMatcher(None, raw_desc, cand_desc).ratio() >= 0.55:
        return True

    return False


def _distractors(
    conn: sqlite3.Connection,
    raw_row,
    exclude_id: int,
    limit: int = 3,
    *,
    min_days: float = 0,
    max_days: float = 3,
) -> list:
    if not raw_row["city"] or not raw_row["event_date"]:
        return []
    rows = conn.execute(
        """
        SELECT * FROM unique_event
        WHERE LOWER(city) = LOWER(?)
          AND id != ?
          AND event_date IS NOT NULL
          AND ABS(julianday(event_date) - julianday(?)) BETWEEN ? AND ?
        ORDER BY ABS(julianday(event_date) - julianday(?))
        LIMIT ?
        """,
        (
            raw_row["city"],
            exclude_id,
            raw_row["event_date"],
            min_days,
            max_days,
            raw_row["event_date"],
            limit * 4,
        ),
    ).fetchall()
    return [r for r in rows if not _looks_like_same_event(raw_row, r)][:limit]


def sample_dedup_match_cases(conn: sqlite3.Connection, n: int) -> list[DedupMatchCase]:
    matched_rows = conn.execute(
        """
        SELECT r.* FROM raw_event r
        WHERE r.deduplication_status = 'matched'
          AND r.unique_event_id IS NOT NULL
          AND r.city IS NOT NULL
          AND r.event_date IS NOT NULL
        """
    ).fetchall()
    random.shuffle(matched_rows)

    n_pos = (n + 1) // 2
    n_neg = n - n_pos
    cases: list[DedupMatchCase] = []
    pos_count = neg_count = 0

    for row in matched_rows:
        if pos_count >= n_pos and neg_count >= n_neg:
            break

        true_row = conn.execute(
            "SELECT * FROM unique_event WHERE id = ?", (row["unique_event_id"],)
        ).fetchone()
        if not true_row:
            continue

        raw_data = _raw_event_data(row)

        if pos_count < n_pos:
            distractor_rows = _distractors(conn, row, exclude_id=row["unique_event_id"])
            candidates = [_unique_event_data(true_row)] + [
                _unique_event_data(d) for d in distractor_rows
            ]
            random.shuffle(candidates)
            cases.append(
                DedupMatchCase(
                    id=f"dm-pos-{row['id']}",
                    tags=["positive", f"candidates_{len(candidates)}"],
                    label_status="labeled",
                    input=DedupMatchInput(raw_event=raw_data, candidates=candidates),
                    expected=DedupMatchExpected(
                        match=True, unique_event_id=row["unique_event_id"]
                    ),
                    metadata=CaseMetadata(
                        source_id=row["source_google_news_id"],
                        notes="bootstrapped from prod LLM match "
                        f"(raw_event {row['id']} -> unique_event {row['unique_event_id']})",
                    ),
                )
            )
            pos_count += 1
        elif neg_count < n_neg:
            # For negatives, require distractors at least 1 day away to avoid
            # picking duplicate rows of the same incident as "non-matches".
            distractor_rows = _distractors(
                conn, row, exclude_id=row["unique_event_id"], min_days=1
            )
            if not distractor_rows:
                continue
            candidates = [_unique_event_data(d) for d in distractor_rows]
            cases.append(
                DedupMatchCase(
                    id=f"dm-neg-{row['id']}",
                    tags=["negative", f"candidates_{len(candidates)}"],
                    label_status="labeled",
                    input=DedupMatchInput(raw_event=raw_data, candidates=candidates),
                    expected=DedupMatchExpected(match=False, unique_event_id=None),
                    metadata=CaseMetadata(
                        source_id=row["source_google_news_id"],
                        notes="true unique_event removed; remaining candidates are "
                        "same-city distractors 1-3 days away",
                    ),
                )
            )
            neg_count += 1

    return cases


def build_fixture(
    db_path: Path,
    n: int,
    seed: int,
    *,
    merge_into: Path | None = None,
) -> tuple[DedupMatchFixture, int]:
    random.seed(seed)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        new_cases = sample_dedup_match_cases(conn, n)
    finally:
        conn.close()

    cases: list[DedupMatchCase] = []
    existing_ids: set[str] = set()
    meta = DedupMatchFixtureMeta(source_db=str(db_path), seed=seed)

    if merge_into and merge_into.exists():
        existing = load_dedup_match_fixture(json.loads(merge_into.read_text()))
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

    fixture = DedupMatchFixture(meta=meta, cases=cases)
    update_dedup_fixture_counts(fixture)
    return fixture, added


def write_fixture(fixture: DedupMatchFixture, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(fixture.model_dump(mode="json"), ensure_ascii=False, indent=2)
    )
