"""Batch pipeline re-run helpers (re-extract, re-enrich, re-geocode, drain)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from loguru import logger
from sqlalchemy import text
from sqlmodel import select

from app.database import async_session_maker
from app.models import RawEvent
from app.services.backfill import (
    ReclassifySignal,
    find_discarded_reclassification_candidates,
    requeue_discarded_sources,
)


def _parse_ids(ids: Sequence[int] | None) -> list[int]:
    if not ids:
        return []
    return [int(i) for i in ids]


def _date_clause(
    column: str,
    *,
    since: date | None,
    until: date | None,
    params: dict[str, Any],
) -> str:
    parts: list[str] = []
    if since is not None:
        params["since"] = since
        parts.append(f"CAST({column} AS DATE) >= :since")
    if until is not None:
        params["until"] = until
        parts.append(f"CAST({column} AS DATE) <= :until")
    return (" AND " + " AND ".join(parts)) if parts else ""


def _location_clause(
    *,
    city: str | None,
    state: str | None,
    params: dict[str, Any],
    city_col: str = "city",
    state_col: str = "state",
) -> str:
    parts: list[str] = []
    if city:
        params["city"] = city.strip().lower()
        parts.append(f"LOWER({city_col}) = :city")
    if state:
        params["state"] = state.strip().lower()
        parts.append(f"LOWER({state_col}) = :state")
    return (" AND " + " AND ".join(parts)) if parts else ""


def _ids_clause(
    column: str,
    ids: Sequence[int],
    params: dict[str, Any],
) -> str:
    if not ids:
        return ""
    # Named bind list for SQLAlchemy text()
    placeholders = []
    for i, value in enumerate(ids):
        key = f"id_{i}"
        params[key] = value
        placeholders.append(f":{key}")
    return f" AND {column} IN ({', '.join(placeholders)})"


# ---------------------------------------------------------------------------
# Candidate selection: re-extract
# ---------------------------------------------------------------------------


async def find_reextract_candidates(
    *,
    limit: int = 100,
    since: date | None = None,
    until: date | None = None,
    city: str | None = None,
    state: str | None = None,
    source_ids: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    """Return extracted sources eligible for in-place re-extraction."""
    ids = _parse_ids(source_ids)
    params: dict[str, Any] = {"lim": limit}
    date_sql = _date_clause("re.event_date", since=since, until=until, params=params)
    loc_sql = _location_clause(city=city, state=state, params=params, city_col="re.city", state_col="re.state")
    ids_sql = _ids_clause("s.id", ids, params)

    # Prefer the raw_event linked to a unique_event; else latest by id.
    query = f"""
        SELECT
            s.id AS source_id,
            s.headline,
            s.publisher_name,
            s.resolved_url,
            s.published_at,
            LENGTH(s.content) AS content_len,
            re.id AS raw_event_id,
            re.unique_event_id,
            re.event_date,
            re.city,
            re.state,
            re.title AS raw_title
        FROM source_google_news s
        INNER JOIN raw_event re ON re.id = (
            SELECT r.id
            FROM raw_event r
            WHERE r.source_google_news_id = s.id
            ORDER BY
                CASE WHEN r.unique_event_id IS NOT NULL THEN 0 ELSE 1 END,
                r.id DESC
            LIMIT 1
        )
        WHERE s.status = 'extracted'
          AND s.content IS NOT NULL
          AND LENGTH(TRIM(s.content)) > 200
          {date_sql}
          {loc_sql}
          {ids_sql}
        ORDER BY re.event_date DESC, s.id DESC
        LIMIT :lim
    """
    async with async_session_maker() as session:
        result = await session.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def dedup_keys_changed(candidate: dict[str, Any], fields: dict[str, Any]) -> bool:
    """True when re-extract changed city/state/event_date (stale unique link risk)."""
    old_city = (candidate.get("city") or "").strip().lower()
    new_city = (fields.get("city") or "").strip().lower()
    old_state = (candidate.get("state") or "").strip().lower()
    new_state = (fields.get("state") or "").strip().lower()
    return (
        old_city != new_city
        or old_state != new_state
        or _as_date(candidate.get("event_date")) != _as_date(fields.get("event_date"))
    )


async def update_raw_event_in_place(
    raw_event_id: int,
    fields: dict[str, Any],
    *,
    unlink_for_rededup: bool = False,
) -> None:
    """Overwrite denormalized + JSON extraction columns on an existing raw_event."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(RawEvent).where(RawEvent.id == raw_event_id)
        )
        raw_event = result.scalar_one_or_none()
        if raw_event is None:
            raise ValueError(f"raw_event {raw_event_id} not found")
        for key, value in fields.items():
            setattr(raw_event, key, value)
        if unlink_for_rededup:
            raw_event.unique_event_id = None
            raw_event.deduplication_status = "pending"
        raw_event.updated_at = datetime.utcnow()
        session.add(raw_event)
        await session.commit()


async def flag_unique_needs_enrichment(unique_event_ids: Iterable[int]) -> int:
    ids = sorted({int(i) for i in unique_event_ids if i is not None})
    if not ids:
        return 0
    params: dict[str, Any] = {}
    ids_sql = _ids_clause("id", ids, params).replace(" AND ", "", 1)
    async with async_session_maker() as session:
        result = await session.execute(
            text(f"""
                UPDATE unique_event
                SET needs_enrichment = true,
                    updated_at = CURRENT_TIMESTAMP
                WHERE {ids_sql}
            """),
            params,
        )
        await session.commit()
        return result.rowcount or 0


async def refresh_unique_source_counts(unique_event_ids: Iterable[int]) -> int:
    """Recompute source_count from currently linked raw_events and flag enrichment."""
    ids = sorted({int(i) for i in unique_event_ids if i is not None})
    if not ids:
        return 0
    params: dict[str, Any] = {}
    ids_sql = _ids_clause("id", ids, params).replace(" AND ", "", 1)
    async with async_session_maker() as session:
        result = await session.execute(
            text(f"""
                UPDATE unique_event u
                SET source_count = (
                        SELECT COUNT(*) FROM raw_event r
                        WHERE r.unique_event_id = u.id
                    ),
                    needs_enrichment = true,
                    updated_at = CURRENT_TIMESTAMP
                WHERE {ids_sql}
            """),
            params,
        )
        await session.commit()
        return result.rowcount or 0


async def reextract_sources(
    *,
    dry_run: bool = True,
    limit: int = 100,
    since: date | None = None,
    until: date | None = None,
    city: str | None = None,
    state: str | None = None,
    source_ids: Sequence[int] | None = None,
    concurrency: int = 5,
) -> dict[str, Any]:
    """In-place re-extract for already-extracted sources (no new raw_event rows)."""
    from app.config import get_settings
    from app.services.extraction import (
        extract_event_from_content,
        raw_event_fields_from_event,
    )

    settings = get_settings()
    candidates = await find_reextract_candidates(
        limit=limit,
        since=since,
        until=until,
        city=city,
        state=state,
        source_ids=source_ids,
    )
    audit: dict[str, Any] = {
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "updated": 0,
        "failed": 0,
        "would_discard": 0,
        "unlinked_for_rededup": 0,
        "flagged_enrichment": 0,
        "samples": [
            {
                "source_id": c["source_id"],
                "raw_event_id": c["raw_event_id"],
                "unique_event_id": c.get("unique_event_id"),
                "city": c.get("city"),
                "event_date": str(c["event_date"]) if c.get("event_date") else None,
                "headline": (c.get("headline") or "")[:120],
            }
            for c in candidates[:50]
        ],
        "failures": [],
        "would_discard_ids": [],
    }
    if dry_run or not candidates:
        return audit

    semaphore = asyncio.Semaphore(concurrency)
    flagged: list[int] = []
    unlinked_parent_ids: list[int] = []
    unlinked = 0

    async def _one(candidate: dict[str, Any]) -> str:
        nonlocal unlinked
        source_id = candidate["source_id"]
        raw_event_id = candidate["raw_event_id"]
        async with semaphore:
            async with async_session_maker() as session:
                row = (
                    await session.execute(
                        text("""
                            SELECT content, headline, published_at, publisher_name, resolved_url
                            FROM source_google_news
                            WHERE id = :id
                        """),
                        {"id": source_id},
                    )
                ).fetchone()
            if not row or not row[0]:
                return "failed"

            content, headline, published_at, publisher_name, resolved_url = row
            original_length = len(content)
            if original_length > settings.extraction_max_chars:
                logger.info(
                    f"[batch reextract] Truncating source {source_id} content from "
                    f"{original_length} to {settings.extraction_max_chars} chars"
                )
                content = content[: settings.extraction_max_chars]
            metadata = {
                "headline": headline,
                "publisher": publisher_name,
                "url": resolved_url,
            }
            if published_at:
                try:
                    pub = published_at
                    if isinstance(pub, str):
                        pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    metadata["published_at"] = pub.strftime("%d/%m/%Y às %H:%M")
                except Exception:
                    metadata["published_at"] = str(published_at)

            try:
                event = await asyncio.to_thread(
                    extract_event_from_content, content, metadata
                )
            except Exception as exc:
                logger.warning(f"[batch reextract] source {source_id} failed: {exc}")
                audit["failures"].append(
                    {"source_id": source_id, "error": str(exc)[:300]}
                )
                return "failed"

            if str(event.content_class) != "incident":
                audit["would_discard_ids"].append(source_id)
                return "would_discard"

            fields = raw_event_fields_from_event(event)
            prior_unique_id = candidate.get("unique_event_id")
            must_unlink = bool(prior_unique_id) and dedup_keys_changed(candidate, fields)
            await update_raw_event_in_place(
                raw_event_id, fields, unlink_for_rededup=must_unlink
            )
            if must_unlink and prior_unique_id:
                unlinked += 1
                unlinked_parent_ids.append(int(prior_unique_id))
            elif prior_unique_id:
                flagged.append(int(prior_unique_id))
            return "updated"

    results = await asyncio.gather(
        *[_one(c) for c in candidates],
        return_exceptions=True,
    )
    normalized: list[str] = []
    for candidate, result in zip(candidates, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(
                f"[batch reextract] source {candidate['source_id']} "
                f"raised: {result}"
            )
            audit["failures"].append(
                {
                    "source_id": candidate["source_id"],
                    "error": str(result)[:300],
                }
            )
            normalized.append("failed")
        else:
            normalized.append(result)

    audit["updated"] = sum(1 for r in normalized if r == "updated")
    audit["failed"] = sum(1 for r in normalized if r == "failed")
    audit["would_discard"] = sum(1 for r in normalized if r == "would_discard")
    audit["unlinked_for_rededup"] = unlinked
    # Always reconcile parents after per-item commits (even if some tasks failed).
    refreshed = await refresh_unique_source_counts(unlinked_parent_ids)
    flagged_only = await flag_unique_needs_enrichment(flagged)
    audit["flagged_enrichment"] = refreshed + flagged_only
    return audit


# ---------------------------------------------------------------------------
# Re-enrich / re-geocode
# ---------------------------------------------------------------------------


async def find_unique_event_ids(
    *,
    limit: int = 500,
    since: date | None = None,
    until: date | None = None,
    city: str | None = None,
    state: str | None = None,
    unique_event_ids: Sequence[int] | None = None,
) -> list[int]:
    ids = _parse_ids(unique_event_ids)
    params: dict[str, Any] = {"lim": limit}
    date_sql = _date_clause("event_date", since=since, until=until, params=params)
    loc_sql = _location_clause(city=city, state=state, params=params)
    ids_sql = _ids_clause("id", ids, params)
    query = f"""
        SELECT id FROM unique_event
        WHERE 1=1
          {date_sql}
          {loc_sql}
          {ids_sql}
        ORDER BY event_date DESC, id DESC
        LIMIT :lim
    """
    async with async_session_maker() as session:
        result = await session.execute(text(query), params)
        return [row[0] for row in result.fetchall()]


async def flag_reenrich(
    *,
    dry_run: bool = True,
    limit: int = 500,
    since: date | None = None,
    until: date | None = None,
    city: str | None = None,
    state: str | None = None,
    unique_event_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    ids = await find_unique_event_ids(
        limit=limit,
        since=since,
        until=until,
        city=city,
        state=state,
        unique_event_ids=unique_event_ids,
    )
    audit: dict[str, Any] = {
        "dry_run": dry_run,
        "candidate_count": len(ids),
        "flagged": 0,
        "unique_event_ids": ids[:100],
    }
    if dry_run or not ids:
        return audit
    audit["flagged"] = await flag_unique_needs_enrichment(ids)
    return audit


async def clear_geocode_for_requeue(
    unique_event_ids: Sequence[int],
) -> int:
    ids = _parse_ids(unique_event_ids)
    if not ids:
        return 0
    params: dict[str, Any] = {}
    ids_sql = _ids_clause("id", ids, params).replace(" AND ", "", 1)
    async with async_session_maker() as session:
        result = await session.execute(
            text(f"""
                UPDATE unique_event
                SET geocoding_source = NULL,
                    latitude = NULL,
                    longitude = NULL,
                    plus_code = NULL,
                    place_id = NULL,
                    formatted_address = NULL,
                    location_precision = NULL,
                    geocoding_confidence = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE {ids_sql}
            """),
            params,
        )
        await session.commit()
        return result.rowcount or 0


async def flag_regeocode(
    *,
    dry_run: bool = True,
    limit: int = 500,
    since: date | None = None,
    until: date | None = None,
    city: str | None = None,
    state: str | None = None,
    unique_event_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    ids = await find_unique_event_ids(
        limit=limit,
        since=since,
        until=until,
        city=city,
        state=state,
        unique_event_ids=unique_event_ids,
    )
    audit: dict[str, Any] = {
        "dry_run": dry_run,
        "candidate_count": len(ids),
        "cleared": 0,
        "unique_event_ids": ids[:100],
    }
    if dry_run or not ids:
        return audit
    audit["cleared"] = await clear_geocode_for_requeue(ids)
    return audit


# ---------------------------------------------------------------------------
# Reclassify wrapper
# ---------------------------------------------------------------------------


async def run_reclassify(
    *,
    dry_run: bool = True,
    limit: int = 500,
    since: date | None = None,
    signal: ReclassifySignal = "all",
) -> dict[str, Any]:
    candidates = await find_discarded_reclassification_candidates(
        limit=limit,
        since=since,
        signal=signal,
    )
    source_ids = [row["id"] for row in candidates]
    audit = await requeue_discarded_sources(source_ids, dry_run=dry_run)
    audit["candidate_count"] = len(candidates)
    audit["signal"] = signal
    audit["samples"] = [
        {
            "id": row["id"],
            "headline": (row.get("headline") or "")[:120],
            "target_status": row["target_status"],
        }
        for row in candidates[:50]
    ]
    return audit


# ---------------------------------------------------------------------------
# Drain / recollect enqueue
# ---------------------------------------------------------------------------

DRAIN_DEFAULTS = {
    "classify": {"limit": 300, "concurrency": 10},
    "download": {"limit": 200},
    "extract": {"limit": 100},
    "dedup": {"limit": 200},
    "enrich": {"limit": 50},
    "geocode": {"limit": 200},
}

ALL_DRAIN_STAGES = ("classify", "download", "extract", "dedup", "enrich", "geocode")


async def enqueue_drain(
    stages: Sequence[str] | None = None,
    *,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Enqueue backlog drain jobs on the namespaced ARQ queue."""
    from app.tasks.worker import create_arq_pool, get_arq_queue_name

    selected = list(stages) if stages else list(ALL_DRAIN_STAGES)
    unknown = [s for s in selected if s not in DRAIN_DEFAULTS]
    if unknown:
        raise ValueError(f"Unknown drain stages: {unknown}")

    limits = limits or {}
    redis = await create_arq_pool()
    enqueued: list[str] = []
    try:
        for stage in selected:
            defaults = DRAIN_DEFAULTS[stage]
            limit = int(limits.get(stage, defaults["limit"]))
            if stage == "classify":
                await redis.enqueue_job(
                    "classify_pending_task",
                    limit=limit,
                    chain_next=False,
                    concurrency=int(defaults.get("concurrency", 10)),
                )
            elif stage == "download":
                await redis.enqueue_job(
                    "download_classified_task", limit=limit, chain_next=False
                )
            elif stage == "extract":
                await redis.enqueue_job(
                    "extract_ready_task", limit=limit, chain_next=False
                )
            elif stage == "dedup":
                await redis.enqueue_job(
                    "batch_dedup_task", limit=limit, chain_next=False
                )
            elif stage == "enrich":
                await redis.enqueue_job(
                    "batch_enrich_task", limit=limit, chain_next=False
                )
            elif stage == "geocode":
                await redis.enqueue_job("batch_geocode_task", limit=limit)
            enqueued.append(f"{stage}:{limit}")
    finally:
        await redis.close()

    return {
        "queue": get_arq_queue_name(),
        "enqueued": enqueued,
    }


async def enqueue_recollect(
    *,
    when: str = "1d",
    full_pipeline: bool = False,
) -> dict[str, Any]:
    from app.tasks.worker import create_arq_pool, get_arq_queue_name

    redis = await create_arq_pool()
    try:
        if full_pipeline:
            job = await redis.enqueue_job(
                "ingest_cities_full_pipeline", when=when
            )
            task = "ingest_cities_full_pipeline"
        else:
            job = await redis.enqueue_job("ingest_cities_task", when=when)
            task = "ingest_cities_task"
    finally:
        await redis.close()

    return {
        "queue": get_arq_queue_name(),
        "task": task,
        "when": when,
        "job_id": getattr(job, "job_id", None),
    }
