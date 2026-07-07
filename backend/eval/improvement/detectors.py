"""Per-stage production anomaly heuristics."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.services.dedup_scan import _date_key, _norm, pair_signal

from eval.improvement.db import SqliteReader, fetch_postgres
from eval.improvement.schemas import ALL_STAGES, AnomalyCandidate, StageName
from eval.stages.classification.build import DEATH_KEYWORDS
from eval.stages.dedup_match.build import _raw_event_data, _unique_event_data, _victim_names

POSITIVE_STATUSES = (
    "ready_for_download",
    "downloading",
    "ready_for_extraction",
    "extracting",
    "extracted",
)


def _candidate_id(stage: str, record_id: int | str) -> str:
    slug = stage.replace("-", "_")
    return f"prod-{slug}-{record_id}"


def _date_str(value: Any) -> str | None:
    if not value:
        return None
    return str(value)[:10]


def _victim_overlap(names_a: list[str], names_b: list[str]) -> bool:
    na = {_norm(n) for n in names_a if n and len(n.strip()) > 3}
    nb = {_norm(n) for n in names_b if n and len(n.strip()) > 3}
    if not na or not nb:
        return False
    if na & nb:
        return True
    for a in na:
        for b in nb:
            if len(a) > 5 and len(b) > 5 and (a in b or b in a):
                return True
    return False


async def detect_classification(db_path: Path | None, limit: int) -> list[AnomalyCandidate]:
    positive_in = ",".join(f"'{s}'" for s in POSITIVE_STATUSES)
    query = f"""
        SELECT id, headline, is_violent_death, status
        FROM source_google_news
        WHERE headline IS NOT NULL
          AND (
            (status = 'discarded' AND is_violent_death = 1)
            OR (status IN ({positive_in}) AND is_violent_death = 0)
          )
        ORDER BY updated_at DESC
        LIMIT :lim
    """
    rows = await _fetch(db_path, query, {"lim": limit * 2})

    keyword_query = """
        SELECT id, headline, is_violent_death, status
        FROM source_google_news
        WHERE status = 'discarded' AND headline IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT :lim
    """
    keyword_rows = await _fetch(db_path, keyword_query, {"lim": limit * 3})
    keyword_hits = [r for r in keyword_rows if DEATH_KEYWORDS.search(r.get("headline") or "")]

    seen: set[int] = set()
    candidates: list[AnomalyCandidate] = []

    for row in rows + keyword_hits:
        source_id = row["id"]
        if source_id in seen:
            continue
        seen.add(source_id)

        status = row.get("status")
        stored = row.get("is_violent_death")
        implied_positive = status in POSITIVE_STATUSES

        if stored == 1 and status == "discarded":
            signal = "false_negative"
            reason = "Stored is_violent_death=true but source was discarded"
        elif stored == 0 and implied_positive:
            signal = "false_positive"
            reason = "Stored is_violent_death=false but source progressed past classification"
        elif DEATH_KEYWORDS.search(row.get("headline") or ""):
            signal = "death_keyword_discarded"
            reason = "Discarded headline contains violent-death keywords"
        else:
            continue

        candidates.append(
            AnomalyCandidate(
                stage="classification",
                candidate_id=_candidate_id("classification", source_id),
                signal=signal,
                reason=reason,
                prod_snapshot={
                    "source_id": source_id,
                    "status": status,
                    "is_violent_death": stored,
                    "headline": (row.get("headline") or "")[:200],
                },
                input={"headline": row.get("headline") or ""},
                record_ids={"source_id": source_id},
            )
        )
        if len(candidates) >= limit:
            break

    return candidates


async def detect_content_gate(db_path: Path | None, limit: int) -> list[AnomalyCandidate]:
    query = """
        SELECT id, headline, content, status, is_violent_death
        FROM source_google_news
        WHERE content IS NOT NULL
          AND length(content) > 500
          AND (
            (status = 'discarded' AND is_violent_death = 1)
            OR (status = 'extracted' AND is_violent_death = 0)
          )
        ORDER BY updated_at DESC
        LIMIT :lim
    """
    rows = await _fetch(db_path, query, {"lim": limit})
    candidates: list[AnomalyCandidate] = []

    for row in rows:
        source_id = row["id"]
        status = row.get("status")
        if status == "discarded":
            signal = "gate_false_negative"
            reason = "Headline passed classification but article was discarded with content available"
        else:
            signal = "gate_false_positive"
            reason = "Source extracted but headline marked non-violent-death"

        candidates.append(
            AnomalyCandidate(
                stage="content-gate",
                candidate_id=_candidate_id("content-gate", source_id),
                signal=signal,
                reason=reason,
                prod_snapshot={
                    "source_id": source_id,
                    "status": status,
                    "is_violent_death": row.get("is_violent_death"),
                    "headline": (row.get("headline") or "")[:120],
                    "content_length": len(row.get("content") or ""),
                },
                input={
                    "headline": row.get("headline") or "",
                    "content": (row.get("content") or "")[:8000],
                },
                record_ids={"source_id": source_id},
            )
        )

    return candidates


async def detect_extraction(db_path: Path | None, limit: int) -> list[AnomalyCandidate]:
    query = """
        SELECT r.id AS raw_event_id, r.title, r.extraction_success,
               s.id AS source_id, s.headline, s.content, s.status
        FROM raw_event r
        JOIN source_google_news s ON r.source_google_news_id = s.id
        WHERE s.content IS NOT NULL
          AND length(s.content) > 300
          AND (r.extraction_success = 0 OR r.extraction_success IS NULL)
        ORDER BY r.id DESC
        LIMIT :lim
    """
    rows = await _fetch(db_path, query, {"lim": limit})
    candidates: list[AnomalyCandidate] = []

    for row in rows:
        raw_id = row["raw_event_id"]
        candidates.append(
            AnomalyCandidate(
                stage="extraction",
                candidate_id=_candidate_id("extraction", raw_id),
                signal="extraction_failed",
                reason="Raw event extraction failed despite stored article content",
                prod_snapshot={
                    "raw_event_id": raw_id,
                    "source_id": row.get("source_id"),
                    "extraction_success": row.get("extraction_success"),
                    "title": (row.get("title") or row.get("headline") or "")[:120],
                },
                input={
                    "headline": row.get("headline") or row.get("title") or "",
                    "content": (row.get("content") or "")[:12000],
                },
                record_ids={"raw_event_id": raw_id, "source_id": row.get("source_id")},
            )
        )

    return candidates


async def detect_dedup_match(db_path: Path | None, limit: int) -> list[AnomalyCandidate]:
    since = (date.today() - timedelta(days=90)).isoformat()
    pair_rows, group_summaries = await _near_duplicate_groups(db_path, since)

    candidates: list[AnomalyCandidate] = []
    for pair in pair_rows[:limit]:
        pair_key = f"{pair['id_a']}-{pair['id_b']}"
        candidates.append(
            AnomalyCandidate(
                stage="dedup-match",
                candidate_id=_candidate_id("dedup-match", pair_key),
                signal="near_duplicate_unique_events",
                reason=(
                    f"Unique events {pair['id_a']} and {pair['id_b']} look like the same incident "
                    f"({pair['signal']}, similarity={pair['similarity']}) but remain separate"
                ),
                prod_snapshot=dict(pair),
                input={"pair": pair},
                record_ids={"id_a": pair["id_a"], "id_b": pair["id_b"]},
            )
        )

    remaining = limit - len(candidates)
    if remaining > 0:
        raw_query = """
            SELECT r.*, ue.id AS matched_ue_id
            FROM raw_event r
            JOIN unique_event ue ON r.unique_event_id = ue.id
            WHERE r.deduplication_status = 'matched'
              AND r.city IS NOT NULL
              AND r.event_date IS NOT NULL
            ORDER BY r.id DESC
            LIMIT :lim
        """
        raw_rows = await _fetch(db_path, raw_query, {"lim": remaining * 5})
        for raw_row in raw_rows:
            sibling_ids = [
                g["member_ids"]
                for g in group_summaries
                if raw_row["matched_ue_id"] in g["member_ids"] and len(g["member_ids"]) > 1
            ]
            if not sibling_ids:
                continue
            members = sibling_ids[0]
            losers = [m for m in members if m != raw_row["matched_ue_id"]]
            if not losers:
                continue
            candidates.append(
                AnomalyCandidate(
                    stage="dedup-match",
                    candidate_id=_candidate_id("dedup-match", f"raw-{raw_row['id']}"),
                    signal="matched_while_sibling_exists",
                    reason=(
                        f"RawEvent {raw_row['id']} matched UE {raw_row['matched_ue_id']} "
                        f"but near-duplicate sibling(s) {losers} still exist"
                    ),
                    prod_snapshot={
                        "raw_event_id": raw_row["id"],
                        "matched_unique_event_id": raw_row["matched_ue_id"],
                        "sibling_ids": losers,
                    },
                    input={"raw_event_id": raw_row["id"], "sibling_ids": losers},
                    record_ids={"raw_event_id": raw_row["id"]},
                )
            )
            if len(candidates) >= limit:
                break

    return candidates[:limit]


async def detect_dedup_cluster(db_path: Path | None, limit: int) -> list[AnomalyCandidate]:
    query = """
        SELECT id, title, event_date, city, state, neighborhood, homicide_type,
               chronological_description, extraction_data, deduplication_status
        FROM raw_event
        WHERE deduplication_status = 'pending'
          AND city IS NOT NULL
          AND event_date IS NOT NULL
        ORDER BY event_date DESC, city, id
    """
    rows = await _fetch(db_path, query, {})
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (_date_str(row.get("event_date")) or "", _norm(row.get("city")))
        buckets[key].append(row)

    candidates: list[AnomalyCandidate] = []
    for (event_day, city), members in buckets.items():
        if len(members) < 2:
            continue
        cluster_members: list[dict] = []
        for i, a in enumerate(members):
            names_a = _victim_names(a.get("extraction_data"))
            for b in members[i + 1 :]:
                names_b = _victim_names(b.get("extraction_data"))
                title_ratio = SequenceMatcher(
                    None, _norm(a.get("title")), _norm(b.get("title"))
                ).ratio()
                if _victim_overlap(names_a, names_b) or title_ratio >= 0.7:
                    if a not in cluster_members:
                        cluster_members.append(a)
                    if b not in cluster_members:
                        cluster_members.append(b)
        if len(cluster_members) < 2:
            continue
        ids = sorted(r["id"] for r in cluster_members)
        group_key = "-".join(str(i) for i in ids[:4])
        candidates.append(
            AnomalyCandidate(
                stage="dedup-cluster",
                candidate_id=_candidate_id("dedup-cluster", group_key),
                signal="pending_overlap_cluster",
                reason=(
                    f"{len(cluster_members)} pending RawEvents in {city} on {event_day} "
                    "share victim/title overlap but were not clustered"
                ),
                prod_snapshot={"event_date": event_day, "city": city, "raw_event_ids": ids},
                input={"raw_event_ids": ids},
                record_ids={"raw_event_ids": ids},
            )
        )
        if len(candidates) >= limit:
            break

    return candidates


async def detect_enrichment(db_path: Path | None, limit: int) -> list[AnomalyCandidate]:
    stale_query = """
        SELECT id, title, city, state, event_date, victim_count, needs_enrichment,
               victims_summary, source_count
        FROM unique_event
        WHERE needs_enrichment = 1
          AND source_count > 0
        ORDER BY id DESC
        LIMIT :lim
    """
    stale_rows = await _fetch(db_path, stale_query, {"lim": limit})
    candidates: list[AnomalyCandidate] = []

    for row in stale_rows:
        ue_id = row["id"]
        candidates.append(
            AnomalyCandidate(
                stage="enrichment",
                candidate_id=_candidate_id("enrichment", ue_id),
                signal="needs_enrichment_stale",
                reason=f"UniqueEvent {ue_id} still flagged needs_enrichment with {row.get('source_count')} sources",
                prod_snapshot=dict(row),
                input={"unique_event_id": ue_id},
                record_ids={"unique_event_id": ue_id},
            )
        )

    remaining = limit - len(candidates)
    if remaining <= 0:
        return candidates

    mismatch_query = """
        SELECT ue.id AS unique_event_id, ue.city AS ue_city, ue.state AS ue_state,
               ue.event_date AS ue_date, ue.victim_count AS ue_victim_count,
               r.id AS raw_event_id, r.city AS raw_city, r.state AS raw_state,
               r.event_date AS raw_date, r.victim_count AS raw_victim_count
        FROM unique_event ue
        JOIN raw_event r ON r.unique_event_id = ue.id
        WHERE ue.source_count > 1
          AND (
            (ue.city IS NOT NULL AND r.city IS NOT NULL AND LOWER(ue.city) != LOWER(r.city))
            OR (ue.victim_count IS NOT NULL AND r.victim_count IS NOT NULL
                AND ue.victim_count != r.victim_count)
          )
        ORDER BY ue.id DESC
        LIMIT :lim
    """
    mismatch_rows = await _fetch(db_path, mismatch_query, {"lim": remaining})
    seen_ue: set[int] = {c.record_ids.get("unique_event_id") for c in candidates if c.record_ids.get("unique_event_id")}

    for row in mismatch_rows:
        ue_id = row["unique_event_id"]
        if ue_id in seen_ue:
            continue
        seen_ue.add(ue_id)
        candidates.append(
            AnomalyCandidate(
                stage="enrichment",
                candidate_id=_candidate_id("enrichment", f"mismatch-{ue_id}"),
                signal="field_mismatch",
                reason=(
                    f"UniqueEvent {ue_id} fields disagree with linked RawEvent {row['raw_event_id']} "
                    "(city or victim_count)"
                ),
                prod_snapshot=dict(row),
                input={"unique_event_id": ue_id},
                record_ids={"unique_event_id": ue_id, "raw_event_id": row["raw_event_id"]},
            )
        )
        if len(candidates) >= limit:
            break

    return candidates


DETECTORS = {
    "classification": detect_classification,
    "content-gate": detect_content_gate,
    "extraction": detect_extraction,
    "dedup-match": detect_dedup_match,
    "dedup-cluster": detect_dedup_cluster,
    "enrichment": detect_enrichment,
}


async def detect_anomalies(
    *,
    db_path: Path | None,
    stages: list[StageName],
    limit: int,
) -> list[AnomalyCandidate]:
    all_candidates: list[AnomalyCandidate] = []
    for stage in stages:
        detector = DETECTORS[stage]
        found = await detector(db_path, limit)
        all_candidates.extend(found)
    return all_candidates


async def _fetch(db_path: Path | None, query: str, params: dict[str, Any]) -> list[dict]:
    if db_path is not None:
        with SqliteReader(db_path) as reader:
            if params:
                return reader.fetchall(_sqlite_params(query), tuple(params.values()))
            return reader.fetchall(query)
    return await fetch_postgres(query, params)


def _sqlite_params(query: str) -> str:
    """Replace :name binds with ? for sqlite3."""
    return re.sub(r":(\w+)", "?", query)


async def _near_duplicate_groups(
    db_path: Path | None, since: str
) -> tuple[list[dict], list[dict]]:
    if db_path is None:
        from app.services.dedup_scan import find_near_duplicate_groups

        return await find_near_duplicate_groups(since)

    query = """
        SELECT id, title, city, state, event_date, neighborhood,
               victims_summary, chronological_description, merged_data,
               source_count
        FROM unique_event
        WHERE event_date >= :since
          AND (content_class IS NULL OR content_class = 'incident')
          AND city IS NOT NULL
          AND event_date IS NOT NULL
        ORDER BY event_date, city, id
    """
    rows = await _fetch(db_path, query, {"since": since})

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (_date_key(row["event_date"]) or "", _norm(row["city"]))
        buckets[key].append(row)

    pair_rows: list[dict] = []
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for (_day, _city), members in buckets.items():
        if len(members) < 2:
            continue
        capped = members[:80]
        for i in range(len(capped)):
            for j in range(i + 1, len(capped)):
                a, b = capped[i], capped[j]
                hit = pair_signal(a, b)
                if not hit:
                    continue
                similarity, signal = hit
                union(a["id"], b["id"])
                pair_rows.append({
                    "id_a": a["id"],
                    "id_b": b["id"],
                    "similarity": round(similarity, 3),
                    "signal": signal,
                    "title_a": (a.get("title") or "")[:120],
                    "title_b": (b.get("title") or "")[:120],
                    "city": a.get("city") or "",
                    "event_date": _date_key(a["event_date"]),
                })

    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if row["id"] in parent:
            root = find(row["id"])
            groups[root].append(row)

    group_summaries = [
        {
            "group_id": root,
            "member_ids": [m["id"] for m in members],
            "city": members[0].get("city"),
            "event_date": _date_key(members[0]["event_date"]),
            "size": len(members),
        }
        for root, members in groups.items()
        if len(members) >= 2
    ]

    return pair_rows, group_summaries


async def load_raw_event_row(db_path: Path | None, raw_event_id: int) -> dict | None:
    rows = await _fetch(
        db_path,
        "SELECT * FROM raw_event WHERE id = :id",
        {"id": raw_event_id},
    )
    return rows[0] if rows else None


async def load_unique_event_row(db_path: Path | None, unique_event_id: int) -> dict | None:
    rows = await _fetch(
        db_path,
        "SELECT * FROM unique_event WHERE id = :id",
        {"id": unique_event_id},
    )
    return rows[0] if rows else None


def raw_event_data_from_row(row: dict) -> dict:
    data = _raw_event_data(row)
    return data.model_dump(mode="json")


def unique_event_data_from_row(row: dict) -> dict:
    data = _unique_event_data(row)
    return data.model_dump(mode="json")
