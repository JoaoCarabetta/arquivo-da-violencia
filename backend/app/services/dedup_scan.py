"""Near-duplicate UniqueEvent detection for maintenance and scripts."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher

from sqlalchemy import text

from app.database import async_session_maker
from app.services.enrichment import FUZZY_TITLE_THRESHOLD
from app.services.maintenance import pick_survivor_id

TITLE_THRESHOLD = FUZZY_TITLE_THRESHOLD
# Soft title floor for same-day/city near-dup scan (ingest blocking stays at 0.80).
SOFT_TITLE_THRESHOLD = 0.72
DESC_THRESHOLD = 0.55
MAX_BUCKET_SIZE = 80

# Tokens that are never treated as person-name keys when taken from narrative summaries.
_NAME_STOPWORDS = {
    "uma",
    "um",
    "o",
    "a",
    "os",
    "as",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "com",
    "foi",
    "vitima",
    "vitimas",
    "homem",
    "mulher",
    "jovem",
    "pessoa",
    "pessoas",
    "trans",
    "anos",
    "ano",
    "nao",
    "identificado",
    "identificada",
    "identificados",
    "identificadas",
    "desconhecido",
    "desconhecida",
    "suspeito",
    "suspeitos",
    "policial",
    "policiais",
    "dois",
    "duas",
    "tres",
    "morto",
    "morta",
    "assassinada",
    "assassinado",
    "encontrado",
    "encontrada",
}

_NAME_PREFIX_RE = re.compile(
    r"^(?:vitima|a vitima|o vitima|uma vitima|um homem|uma mulher|pessoa)\s+",
    re.IGNORECASE,
)
_AGE_TAIL_RE = re.compile(
    r",?\s*\d{1,3}\s*anos?\b.*$",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\([^)]*\)")


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


def _looks_like_person_name(norm: str) -> bool:
    """Reject narrative fragments mistaken for names (e.g. 'uma mulher trans de 45 anos')."""
    if not norm or len(norm) < 3:
        return False
    tokens = [t for t in re.split(r"[^\w]+", norm) if t]
    if not tokens:
        return False
    if len(tokens) > 6:
        return False
    if any(ch.isdigit() for ch in norm):
        return False
    content = [t for t in tokens if t not in _NAME_STOPWORDS]
    if len(content) < 1:
        return False
    # Allow short first names / nicknames (Wal, Ana) when they are the only token.
    if len(content) == 1 and len(content[0]) < 3:
        return False
    stop_ratio = 1 - (len(content) / max(len(tokens), 1))
    if stop_ratio > 0.5 and len(content) < 2:
        return False
    return True


def _add_name_keys(keys: set[str], name: str | None) -> None:
    if not name or len(name.strip()) < 3:
        return
    cleaned = _PAREN_RE.sub(" ", name)
    cleaned = _NAME_PREFIX_RE.sub("", cleaned.strip())
    cleaned = _AGE_TAIL_RE.sub("", cleaned).strip(" ,;-")
    # Prefer text before first sentence-like break for narrative summaries.
    for sep in (". ", "; ", " foi ", " morreu ", " morta ", " morto "):
        if sep in cleaned.lower():
            # Only split on Portuguese narrative verbs when the head looks short.
            idx = cleaned.lower().find(sep)
            head = cleaned[:idx].strip(" ,;-")
            if 3 <= len(head) <= 60:
                cleaned = head
            break
    # First comma often separates name from age/role — but only if left side looks like a name.
    if "," in cleaned:
        head = cleaned.split(",", 1)[0].strip()
        if _looks_like_person_name(_norm(head)):
            cleaned = head

    norm = _norm(cleaned)
    if not _looks_like_person_name(norm):
        return
    keys.add(norm)
    tokens = [t for t in norm.split() if t not in _NAME_STOPWORDS]
    if len(tokens) >= 2:
        keys.add(f"{tokens[0]} {tokens[-1]}")
        for a, b in zip(tokens, tokens[1:]):
            keys.add(f"{a} {b}")
    elif len(tokens) == 1 and len(tokens[0]) >= 3:
        keys.add(tokens[0])


def _victim_name_keys(row: dict) -> set[str]:
    keys: set[str] = set()

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
                _add_name_keys(keys, (victim or {}).get("name"))

    summary = row.get("victims_summary") or ""
    if summary:
        # Prefer a short leading name clause; ignore long narrative dumps.
        head = summary.split("\n", 1)[0].strip()
        _add_name_keys(keys, head)

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


def _mo_context_overlap(row_a: dict, row_b: dict) -> bool:
    """Same-day/city MO overlap when names disagree or one side is anonymous.

    Conservative: requires several distinctive shared tokens from description/summary.
    """
    text_a = _norm(
        " ".join(
            filter(
                None,
                [
                    row_a.get("chronological_description"),
                    row_a.get("victims_summary"),
                    row_a.get("neighborhood"),
                ],
            )
        )
    )
    text_b = _norm(
        " ".join(
            filter(
                None,
                [
                    row_b.get("chronological_description"),
                    row_b.get("victims_summary"),
                    row_b.get("neighborhood"),
                ],
            )
        )
    )
    if len(text_a) < 40 or len(text_b) < 40:
        return False

    # Distinctive multi-word / numeric cues that rarely collide across unrelated crimes.
    cues = [
        r"\b\d{2,}\s*(?:facadas|golpes|tiros|disparos|perfura[cç][oõ]es)\b",
        r"\b(?:kitnet|quadra\s+\d+|arno\s*\d+|305\s*norte)\b",
        r"\b(?:operacao\s+jovem\s+guerreiro|batalhao\s+de\s+choque)\b",
        r"\b(?:hospital\s+clinica\s+sul|avenida\s+cassiano\s+ricardo)\b",
        r"\b(?:mais\s+de\s+30\s+tiros|mais\s+de\s+30\s+disparos)\b",
        r"\b(?:esposa\s+e\s+(?:o\s+)?filho|esposa\s+e\s+filho)\b",
        r"\b(?:cinco\s+(?:suspeitos|individuos|homens)\s+(?:armados|mascarados))\b",
        r"\b(?:tentou\s+incendiar|tentativa\s+de\s+(?:inc[eê]ndio|queima))\b",
    ]
    shared = 0
    for pattern in cues:
        if re.search(pattern, text_a) and re.search(pattern, text_b):
            shared += 1
    if shared >= 1 and SequenceMatcher(None, text_a[:400], text_b[:400]).ratio() >= 0.28:
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
        if ratio >= SOFT_TITLE_THRESHOLD and _mo_context_overlap(row_a, row_b):
            return ratio, "title_soft_mo"

    desc_a = _norm(row_a.get("chronological_description"))[:300]
    desc_b = _norm(row_b.get("chronological_description"))[:300]
    if desc_a and desc_b:
        ratio = SequenceMatcher(None, desc_a, desc_b).ratio()
        if ratio >= DESC_THRESHOLD:
            return ratio, "description_fuzzy"

    # Named vs anonymous (or conflicting names) with strong shared MO on same bucket.
    if _mo_context_overlap(row_a, row_b):
        # If both sides have real names that clearly differ, still allow MO signal —
        # LLM match / human ops confirm before merge in production paths that use this.
        return 0.85, "mo_context"

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


def _scan_bucket_for_near_duplicates(
    members: list[dict],
    *,
    event_day: str = "",
    city: str = "",
) -> tuple[list[dict], list[dict]]:
    """Scan one date/city bucket and return (pair_rows, group_summaries)."""
    uf = _UnionFind()
    pair_rows: list[dict] = []

    if len(members) < 2:
        return pair_rows, []

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
                "city": a.get("city") or city,
                "event_date": event_day or _date_key(a.get("event_date")) or "",
                "source_count_a": a.get("source_count") or 1,
                "source_count_b": b.get("source_count") or 1,
                "suggested_survivor_id": survivor_id,
            })

    groups: dict[int, list[dict]] = defaultdict(list)
    for row in members:
        if row["id"] in uf.parent:
            root = uf.find(row["id"])
            groups[root].append(row)

    group_summaries = []
    for root, group_members in groups.items():
        if len(group_members) < 2:
            continue
        survivor_id = pick_survivor_id(
            [
                {"id": m["id"], "source_count": m.get("source_count") or 1}
                for m in group_members
            ]
        )
        group_summaries.append({
            "group_id": root,
            "member_ids": [m["id"] for m in group_members],
            "survivor_id": survivor_id,
            "loser_ids": [m["id"] for m in group_members if m["id"] != survivor_id],
            "city": group_members[0].get("city") or city,
            "event_date": event_day or _date_key(group_members[0]["event_date"]),
            "size": len(group_members),
        })

    for pair in pair_rows:
        pair["group_id"] = uf.find(pair["id_a"])

    return pair_rows, group_summaries


async def find_near_duplicate_groups_in_bucket(
    event_date: str | date | None,
    city: str | None,
) -> list[dict]:
    """Return near-duplicate group summaries for one date/city bucket."""
    if not city:
        return []

    day_key = _date_key(event_date)
    if not day_key:
        return []

    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT id, title, city, state, event_date, neighborhood,
                       victims_summary, chronological_description, merged_data,
                       source_count
                FROM unique_event
                WHERE LOWER(TRIM(city)) = LOWER(TRIM(:city))
                  AND date(event_date) = :event_date
                  AND (content_class IS NULL OR content_class = 'incident')
                ORDER BY id
            """),
            {"city": city, "event_date": day_key},
        )
        members = [dict(r._mapping) for r in result.fetchall()]

    _, group_summaries = _scan_bucket_for_near_duplicates(
        members,
        event_day=day_key,
        city=city,
    )
    return group_summaries


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

    pair_rows: list[dict] = []
    group_summaries: list[dict] = []

    for (event_day, city), members in buckets.items():
        bucket_pairs, bucket_groups = _scan_bucket_for_near_duplicates(
            members,
            event_day=event_day,
            city=city,
        )
        pair_rows.extend(bucket_pairs)
        group_summaries.extend(bucket_groups)

    return pair_rows, group_summaries
