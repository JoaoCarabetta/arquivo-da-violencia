"""One-shot production backfill helpers (reclassify, requeue)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from sqlalchemy import text

from app.database import async_session_maker
from app.services.classification_heuristics import should_force_violent_death

ReclassifySignal = Literal["all", "death_keywords", "heuristic_true", "false_negative"]

_DEATH_KEYWORDS = re.compile(
    r"\b(morto|morta|mortos|mortas|assassin|homicíd|homicid|executad|"
    r"corpo|feminicíd|feminicid|latrocín|latrocin|assassinat|crivad|"
    r"neutralizad|chacina|carbonizad|linchad|tombou|tombaram)\b",
    re.IGNORECASE,
)

POSITIVE_STATUSES = (
    "ready_for_download",
    "downloading",
    "ready_for_extraction",
    "extracting",
    "extracted",
)


def _matches_signal(
    row: dict[str, Any],
    signal: ReclassifySignal,
) -> bool:
    headline = row.get("headline") or ""
    status = row.get("status")
    stored = row.get("is_violent_death")

    if signal == "false_negative":
        return stored is True or stored == 1
    if signal == "death_keywords":
        return bool(_DEATH_KEYWORDS.search(headline))
    if signal == "heuristic_true":
        return should_force_violent_death(headline)
    # all: union of heuristics used in prod anomaly detection
    if stored is True or stored == 1:
        return True
    if status in POSITIVE_STATUSES and (stored is False or stored == 0):
        return False
    if _DEATH_KEYWORDS.search(headline):
        return True
    if should_force_violent_death(headline):
        return True
    return False


def _target_status(row: dict[str, Any]) -> str:
    """Pick pipeline status after requeue."""
    if row.get("has_content"):
        return "ready_for_extraction"
    if row.get("is_violent_death") in (True, 1):
        return "ready_for_download"
    return "ready_for_classification"


async def find_discarded_reclassification_candidates(
    *,
    limit: int = 500,
    since: date | None = None,
    signal: ReclassifySignal = "all",
) -> list[dict[str, Any]]:
    """Return discarded sources that look like classification false negatives."""
    params: dict[str, Any] = {"lim": limit * 5}
    since_clause = ""
    if since:
        since_clause = "AND updated_at >= :since"
        params["since"] = since

    query = f"""
        SELECT id, headline, status, is_violent_death,
               CASE WHEN content IS NULL THEN 0 ELSE LENGTH(content) END AS content_len,
               content IS NOT NULL AND LENGTH(TRIM(content)) > 200 AS has_content
        FROM source_google_news
        WHERE status = 'discarded'
          AND headline IS NOT NULL
          {since_clause}
        ORDER BY updated_at DESC
        LIMIT :lim
    """
    async with async_session_maker() as session:
        result = await session.execute(text(query), params)
        rows = [dict(row._mapping) for row in result.fetchall()]

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not _matches_signal(row, signal):
            continue
        row["target_status"] = _target_status(row)
        candidates.append(row)
        if len(candidates) >= limit:
            break
    return candidates


async def requeue_discarded_sources(
    source_ids: list[int],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Requeue discarded sources for classification/download/extraction."""
    if not source_ids:
        return {
            "dry_run": dry_run,
            "requested": 0,
            "requeued": 0,
            "by_target_status": {},
            "source_ids": [],
        }

    id_list = ",".join(str(source_id) for source_id in source_ids)
    select_query = f"""
        SELECT id, headline, is_violent_death,
               content IS NOT NULL AND LENGTH(TRIM(content)) > 200 AS has_content
        FROM source_google_news
        WHERE id IN ({id_list}) AND status = 'discarded'
    """
    async with async_session_maker() as session:
        result = await session.execute(text(select_query))
        rows = [dict(row._mapping) for row in result.fetchall()]

    by_status: dict[str, list[int]] = {
        "ready_for_classification": [],
        "ready_for_download": [],
        "ready_for_extraction": [],
    }
    for row in rows:
        target = _target_status(row)
        by_status[target].append(row["id"])

    audit: dict[str, Any] = {
        "dry_run": dry_run,
        "requested": len(source_ids),
        "requeued": 0,
        "by_target_status": {k: len(v) for k, v in by_status.items() if v},
        "source_ids": [],
    }

    if dry_run:
        audit["source_ids"] = [row["id"] for row in rows]
        audit["requeued"] = len(rows)
        return audit

    async with async_session_maker() as session:
        for target_status, ids in by_status.items():
            if not ids:
                continue
            ids_sql = ",".join(str(i) for i in ids)
            await session.execute(
                text(f"""
                    UPDATE source_google_news
                    SET status = :target_status,
                        is_violent_death = NULL,
                        classification_confidence = NULL,
                        classification_reasoning = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({ids_sql}) AND status = 'discarded'
                """),
                {"target_status": target_status},
            )
            audit["requeued"] += len(ids)
            audit["source_ids"].extend(ids)
        await session.commit()

    return audit
