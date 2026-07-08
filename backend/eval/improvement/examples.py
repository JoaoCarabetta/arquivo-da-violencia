"""Real production examples that justify each diagnosis fix."""

from __future__ import annotations

import re
from typing import Any

from eval.improvement.schemas import AffectedGroup, AnomalyCandidate, FixCluster


def _clip(text: str | None, n: int = 140) -> str:
    if not text:
        return "—"
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _highlight_overlap(text_a: str, text_b: str) -> str | None:
    """Return a short phrase describing obvious overlap between two strings."""
    a, b = _clip(text_a, 200).lower(), _clip(text_b, 200).lower()
    if not a or not b or a == "—" or b == "—":
        return None
    # Named victim: look for capitalized multi-word name in both
    names_a = re.findall(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){1,4}", text_a)
    for name in names_a:
        if len(name) > 8 and name.lower() in b:
            return f"Same victim name in both records: **{name}**"
    if a in b or b in a:
        return "One title is a substring of the other"
    tokens_a = set(re.findall(r"\w{4,}", a))
    tokens_b = set(re.findall(r"\w{4,}", b))
    shared = tokens_a & tokens_b
    location_hints = {t for t in shared if t not in {"homicidio", "homicídio", "feminicidio", "feminicídio", "qualificado", "residencia", "residência", "publica", "pública"}}
    if location_hints:
        top = sorted(location_hints, key=len, reverse=True)[:3]
        return f"Shared location/topic tokens: {', '.join(f'`{t}`' for t in top)}"
    return None


class ExampleDb:
    """Read-only DB accessor for example enrichment."""

    def __init__(self, enricher: Any) -> None:
        self._db = enricher

    def unique_event(self, ue_id: int) -> dict[str, Any] | None:
        if not self._db._conn:
            return None
        row = self._db._conn.execute(
            "SELECT id, title, city, state, event_date, victims_summary, source_count "
            "FROM unique_event WHERE id = ?",
            (ue_id,),
        ).fetchone()
        return dict(row) if row else None

    def raw_event(self, raw_id: int) -> dict[str, Any] | None:
        if not self._db._conn:
            return None
        row = self._db._conn.execute(
            "SELECT id, title, city, state, event_date, deduplication_status, "
            "victim_count, unique_event_id FROM raw_event WHERE id = ?",
            (raw_id,),
        ).fetchone()
        return dict(row) if row else None

    def enrichment_rows(self, ue_id: int) -> list[dict[str, Any]]:
        if not self._db._conn:
            return []
        rows = self._db._conn.execute(
            """
            SELECT ue.id AS ue_id, ue.title, ue.city AS ue_city, ue.victim_count AS ue_victim_count,
                   r.id AS raw_id, r.title AS raw_title, r.city AS raw_city,
                   r.victim_count AS raw_victim_count
            FROM unique_event ue
            JOIN raw_event r ON r.unique_event_id = ue.id
            WHERE ue.id = ?
            ORDER BY r.id
            """,
            (ue_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _pair_evidence(
    group: AffectedGroup,
    candidates_by_id: dict[str, AnomalyCandidate],
) -> AnomalyCandidate | None:
    for cid in group.candidate_ids:
        c = candidates_by_id.get(cid)
        if c and c.prod_snapshot.get("similarity") is not None:
            return c
    for cid in group.candidate_ids:
        if cid in candidates_by_id:
            return candidates_by_id[cid]
    return None


def _format_dedup_match_group_example(
    group: AffectedGroup,
    db: ExampleDb,
    candidates_by_id: dict[str, AnomalyCandidate],
) -> list[str]:
    ue_ids = group.unique_event_ids[:4]
    if len(group.unique_event_ids) > 4:
        ue_ids_note = f" (showing 4 of {len(group.unique_event_ids)})"
    else:
        ue_ids_note = ""

    lines = [
        f"**Example: {group.label}**{ue_ids_note}",
        "",
        "| UE | Title | Victim(s) | Sources |",
        "|----|-------|-----------|---------|",
    ]
    rows: list[dict[str, Any]] = []
    for ue_id in ue_ids:
        row = db.unique_event(ue_id)
        if row:
            rows.append(row)
            lines.append(
                f"| `{row['id']}` | {_clip(row.get('title'), 70)} | "
                f"{_clip(row.get('victims_summary'), 90)} | {row.get('source_count') or 0} |"
            )

    pair = _pair_evidence(group, candidates_by_id)
    lines.append("")
    if len(rows) >= 2:
        overlap = _highlight_overlap(
            str(rows[0].get("victims_summary") or rows[0].get("title")),
            str(rows[1].get("victims_summary") or rows[1].get("title")),
        )
        if overlap:
            lines.append(f"**Why this is one incident:** {overlap}.")
        else:
            lines.append(
                f"**Why this is one incident:** Same city and date (`{group.label}`); "
                f"multiple sources describe the same event with slightly different headlines."
            )
    if pair:
        snap = pair.prod_snapshot
        sig = snap.get("signal") or pair.signal
        sim = snap.get("similarity")
        sim_str = f", similarity={sim}" if sim is not None else ""
        lines.append(
            f"Detection signal: `{sig}`{sim_str} on pair "
            f"UE `{snap.get('id_a')}` ↔ UE `{snap.get('id_b')}`."
        )
    if group.suggested_survivor_id:
        lines.append(
            f"After merge: keep UE `{group.suggested_survivor_id}`, "
            f"relink raw events from {len(group.unique_event_ids) - 1} loser UE(s)."
        )
    return lines


def _format_dedup_cluster_group_example(group: AffectedGroup, db: ExampleDb) -> list[str]:
    raw_ids = group.raw_event_ids[:5]
    note = f" (showing {len(raw_ids)} of {len(group.raw_event_ids)})" if len(group.raw_event_ids) > 5 else ""

    lines = [
        f"**Example: {group.label}**{note}",
        "",
        "These raw events are still `pending` but describe the same incident:",
        "",
        "| Raw | Title | Status |",
        "|-----|-------|--------|",
    ]
    titles: list[str] = []
    for raw_id in raw_ids:
        row = db.raw_event(raw_id)
        if row:
            titles.append(str(row.get("title") or ""))
            lines.append(
                f"| `{row['id']}` | {_clip(row.get('title'), 85)} | `{row.get('deduplication_status')}` |"
            )

    lines.append("")
    if len(titles) >= 2:
        overlap = _highlight_overlap(titles[0], titles[1])
        if overlap:
            lines.append(f"**Why they should cluster:** {overlap}.")
        else:
            lines.append(
                "**Why they should cluster:** Same city and date; overlapping headlines from "
                "different news sources about one event."
            )
    lines.append(
        "**Why the fix applies:** Batch dedup (`process_pending_deduplication`) should create "
        "one UniqueEvent and link all of these — they never left `pending`."
    )
    return lines


def _format_enrichment_group_example(
    group: AffectedGroup,
    db: ExampleDb,
    candidate: AnomalyCandidate | None,
) -> list[str]:
    ue_id = group.unique_event_ids[0] if group.unique_event_ids else None
    if not ue_id and candidate:
        ue_id = candidate.input.get("unique_event_id") or candidate.prod_snapshot.get("unique_event_id")
    if not ue_id:
        return [f"**Example: {group.label}** — (no UE in snapshot)"]

    rows = db.enrichment_rows(int(ue_id))
    ue_row = db.unique_event(int(ue_id))
    lines = [
        f"**Example: UE `{ue_id}`** — {_clip(ue_row.get('title') if ue_row else None, 80)}",
        "",
        "| Raw | Raw victims | UE victims | Mismatch |",
        "|-----|-------------|------------|----------|",
    ]
    ue_vc = rows[0]["ue_victim_count"] if rows else None
    mismatches: list[str] = []
    for row in rows[:4]:
        raw_vc = row.get("raw_victim_count")
        mismatch = raw_vc is not None and ue_vc is not None and raw_vc != ue_vc
        flag = "⚠️ count" if mismatch else "—"
        if mismatch:
            mismatches.append(f"Raw `{row['raw_id']}` says {raw_vc} victims, UE says {ue_vc}")
        lines.append(
            f"| `{row['raw_id']}` | {raw_vc if raw_vc is not None else '?'} | "
            f"{ue_vc if ue_vc is not None else '?'} | {flag} |"
        )

    lines.append("")
    if mismatches:
        lines.append(f"**Why this is wrong:** {'; '.join(mismatches)}.")
        lines.append(
            "**Why the fix applies:** Enrichment should reconcile victim_count from linked "
            "RawEvents (e.g. prefer majority or most recent extraction), not leave stale values."
        )
    elif candidate:
        snap = candidate.prod_snapshot
        if snap.get("ue_city") and snap.get("raw_city"):
            lines.append(
                f"**Why this is wrong:** UE city=`{snap.get('ue_city')}` vs Raw `{snap.get('raw_event_id')}` "
                f"city=`{snap.get('raw_city')}`."
            )
    return lines


def build_fix_examples(
    cluster: FixCluster,
    candidates_by_id: dict[str, AnomalyCandidate],
    db_enricher: Any,
    *,
    max_groups: int = 2,
) -> list[str]:
    """Build markdown lines with real prod examples for one fix cluster."""
    db = ExampleDb(db_enricher)
    if not db._db._conn:
        return ["*(Connect `--db` snapshot for real examples)*"]

    lines = ["**Real examples (why this fix makes sense):**", ""]

    groups = sorted(
        cluster.affected,
        key=lambda g: g.pair_count or len(g.raw_event_ids) or len(g.unique_event_ids),
        reverse=True,
    )[:max_groups]

    if cluster.stage == "dedup-match":
        for group in groups:
            lines.extend(_format_dedup_match_group_example(group, db, candidates_by_id))
            lines.append("")
    elif cluster.stage == "dedup-cluster":
        for group in groups:
            lines.extend(_format_dedup_cluster_group_example(group, db))
            lines.append("")
    elif cluster.stage == "enrichment":
        for group in groups:
            cid = group.candidate_ids[0] if group.candidate_ids else None
            cand = candidates_by_id.get(cid) if cid else None
            lines.extend(_format_enrichment_group_example(group, db, cand))
            lines.append("")
    else:
        for group in groups[:1]:
            cid = group.candidate_ids[0] if group.candidate_ids else None
            cand = candidates_by_id.get(cid) if cid else None
            if cand:
                snap = cand.prod_snapshot
                lines.append(f"**Example:** {_clip(snap.get('headline') or snap.get('title'), 120)}")
                lines.append(f"Signal: `{cand.signal}` — {cand.reason}")
                lines.append("")

    return lines
