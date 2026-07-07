"""Near-duplicate UniqueEvent detection for maintenance and scripts."""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher

from sqlalchemy import text

from app.database import async_session_maker
from app.services.enrichment import FUZZY_TITLE_THRESHOLD
from app.services.maintenance import pick_survivor_id

TITLE_THRESHOLD = FUZZY_TITLE_THRESHOLD
DESC_THRESHOLD = 0.55
MAX_BUCKET_SIZE = 80


def _norm(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text.lower().strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split())


def _date_key(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _victim_name_keys(row: dict) -> set[str]:
    keys: set[str] = set()
    summary = row.get("victims_summary") or ""
    if summary:
        name = summary.split(",")[0].strip()
        norm = _norm(name)
        if len(norm) > 3:
            keys.add(norm)
            tokens = norm.split()
            if len(tokens) >= 2:
                keys.add(f"{tokens[0]} {tokens[-1]}")
                for a, b in zip(tokens, tokens[1:]):
                    keys.add(f"{a} {b}")

    merged = row.get("merged_data")
    if merged:
        if isinstance(merged, str):
            try:
                merged = json.loads(merged)
            except json.JSONDecodeError:
                merged = None
        if isinstance(merged, dict):
            victims = (merged.get("victims") or {}).get("identifiable_victims") or []
            for victim in victims:
                name = (victim or {}).get("name")
                if name and len(name.strip()) > 3:
                    norm = _norm(name)
                    keys.add(norm)
                    tokens = norm.split()
                    if len(tokens) >= 2:
                        keys.add(f"{tokens[0]} {tokens[-1]}")
    return keys


def _victim_overlap(keys_a: set[str], keys_b: set[str]) -> bool:
    if not keys_a or not keys_b:
        return False
    if keys_a & keys_b:
        return True
    for ka in keys_a:
        for kb in keys_b:
            if len(ka) > 5 and len(kb) > 5 and (ka in kb or kb in ka):
                return True
    return False


def pair_signal(row_a: dict, row_b: dict) -> tuple[float, str] | None:
    keys_a = _victim_name_keys(row_a)
    keys_b = _victim_name_keys(row_b)
    if _victim_overlap(keys_a, keys_b):
        return 1.0, "victim_name"

    title_a, title_b = _norm(row_a.get("title")), _norm(row_b.get("title"))
    if title_a and title_b:
        if title_a in title_b or title_b in title_a:
            return 0.95, "title_substring"
        ratio = SequenceMatcher(None, title_a, title_b).ratio()
        if ratio >= TITLE_THRESHOLD:
            return ratio, "title_fuzzy"

    desc_a = _norm(row_a.get("chronological_description"))[:300]
    desc_b = _norm(row_b.get("chronological_description"))[:300]
    if desc_a and desc_b:
        ratio = SequenceMatcher(None, desc_a, desc_b).ratio()
        if ratio >= DESC_THRESHOLD:
            return ratio, "description_fuzzy"

    return None


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _parse_since(since: str | date) -> date:
    if isinstance(since, date):
        return since
    return date.fromisoformat(since)


async def find_near_duplicate_groups(since: str | date) -> tuple[list[dict], list[dict]]:
    """Return (pair_rows, group_summaries)."""
    since_date = _parse_since(since)
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT id, title, city, state, event_date, neighborhood,
                       victims_summary, chronological_description, merged_data,
                       source_count
                FROM unique_event
                WHERE event_date >= :since
                  AND (content_class IS NULL OR content_class = 'incident')
                  AND city IS NOT NULL
                  AND event_date IS NOT NULL
                ORDER BY event_date, city, id
            """),
            {"since": since_date},
        )
        rows = [dict(r._mapping) for r in result.fetchall()]

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (_date_key(row["event_date"]) or "", _norm(row["city"]))
        buckets[key].append(row)

    uf = _UnionFind()
    pair_rows: list[dict] = []

    for (event_day, city), members in buckets.items():
        if len(members) < 2:
            continue
        if len(members) > MAX_BUCKET_SIZE:
            members = members[:MAX_BUCKET_SIZE]

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                hit = pair_signal(a, b)
                if not hit:
                    continue
                similarity, signal = hit
                uf.union(a["id"], b["id"])
                survivor_id = pick_survivor_id(
                    [
                        {"id": a["id"], "source_count": a.get("source_count") or 1},
                        {"id": b["id"], "source_count": b.get("source_count") or 1},
                    ]
                )
                pair_rows.append({
                    "id_a": a["id"],
                    "id_b": b["id"],
                    "similarity": round(similarity, 3),
                    "signal": signal,
                    "title_a": (a.get("title") or "")[:120],
                    "title_b": (b.get("title") or "")[:120],
                    "city": a.get("city") or "",
                    "event_date": event_day,
                    "source_count_a": a.get("source_count") or 1,
                    "source_count_b": b.get("source_count") or 1,
                    "suggested_survivor_id": survivor_id,
                })

    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if row["id"] in uf.parent:
            root = uf.find(row["id"])
            groups[root].append(row)

    group_summaries = []
    for root, members in groups.items():
        if len(members) < 2:
            continue
        survivor_id = pick_survivor_id(
            [{"id": m["id"], "source_count": m.get("source_count") or 1} for m in members]
        )
        group_summaries.append({
            "group_id": root,
            "member_ids": [m["id"] for m in members],
            "survivor_id": survivor_id,
            "loser_ids": [m["id"] for m in members if m["id"] != survivor_id],
            "city": members[0].get("city"),
            "event_date": _date_key(members[0]["event_date"]),
            "size": len(members),
        })

    for pair in pair_rows:
        pair["group_id"] = uf.find(pair["id_a"])

    return pair_rows, group_summaries
