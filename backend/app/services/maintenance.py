"""Maintenance helpers for recovering the pipeline from stuck states."""

from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.services import diagnostics
from app.services.enrichment import normalize_title


# Map of transient "claimed" statuses back to the queue status they should
# return to if a worker crashed / errored out mid-processing and left the row
# stranded. These intermediate states are only valid while a task is actively
# working a row; anything older than the threshold is safe to requeue.
STUCK_STATUS_RESETS = {
    "classifying": "ready_for_classification",
    "downloading": "ready_for_download",
    "extracting": "ready_for_extraction",
}

GEOCODING_FIELDS = (
    "latitude",
    "longitude",
    "plus_code",
    "place_id",
    "formatted_address",
    "location_precision",
    "geocoding_source",
    "geocoding_confidence",
)


def normalize_city(city: str | None) -> str:
    """Normalize city for duplicate grouping (same rules as title)."""
    return normalize_title(city or "")


def _event_date_key(event_date: datetime | date | str | None) -> str | None:
    if event_date is None:
        return None
    if isinstance(event_date, datetime):
        return event_date.date().isoformat()
    if isinstance(event_date, date):
        return event_date.isoformat()
    if isinstance(event_date, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(event_date, fmt).date().isoformat()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(event_date.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None
    return None


def duplicate_group_key(
    title: str | None,
    city: str | None,
    event_date: datetime | date | None,
) -> tuple[str, str, str] | None:
    """Build a normalized grouping key for exact duplicate detection."""
    normalized_title = normalize_title(title or "")
    normalized_city = normalize_city(city)
    date_key = _event_date_key(event_date)
    if not normalized_title or not normalized_city or not date_key:
        return None
    return normalized_title, normalized_city, date_key


def pick_survivor_id(event_ids: list[dict[str, Any]]) -> int:
    """Pick canonical UniqueEvent: highest source_count, then lowest id."""
    return min(event_ids, key=lambda row: (-row["source_count"], row["id"]))["id"]


async def recover_stuck_sources(older_than_minutes: int = 15) -> dict:
    """
    Requeue sources stranded in transient processing states.

    A row gets a transient status (e.g. 'classifying') when a batch task
    atomically claims it. If the task then fails for an infrastructure reason
    (pool exhaustion, lock timeout, worker restart) the row can be left stuck
    in that status forever and never reprocessed. This resets any such row that
    has not been touched within ``older_than_minutes`` back to its queue status.

    Args:
        older_than_minutes: Only reset rows whose ``updated_at`` is older than
            this many minutes, to avoid disturbing in-flight work.

    Returns:
        Dict mapping each transient status to the number of rows requeued.
    """
    recovered: dict[str, int] = {}
    async with async_session_maker() as session:
        for stuck_status, target_status in STUCK_STATUS_RESETS.items():
            result = await session.execute(
                text(f"""
                    UPDATE source_google_news
                    SET status = :target_status, updated_at = CURRENT_TIMESTAMP
                    WHERE status = :stuck_status
                    AND updated_at < datetime('now', '-{int(older_than_minutes)} minutes')
                """),
                {"target_status": target_status, "stuck_status": stuck_status},
            )
            recovered[stuck_status] = result.rowcount or 0
        await session.commit()

    total = sum(recovered.values())
    if total:
        logger.info(f"[RECOVERY] Requeued {total} stuck sources: {recovered}")
    else:
        logger.info("[RECOVERY] No stuck sources to requeue")

    return recovered


# Map each terminal failure status to the queue status it should return to when
# its most recent failure was transient and it still has retry budget left.
RETRYABLE_FAILURE_RESETS = {
    "failed_in_download": ("download", "ready_for_download"),
    "failed_in_extraction": ("extraction", "ready_for_extraction"),
}


async def requeue_retryable_failures(max_attempts: int | None = None) -> dict:
    """Requeue items whose latest failure was transient and have retry budget.

    A source ends in ``failed_in_download`` / ``failed_in_extraction`` for many
    reasons. Some are transient (timeouts, 5xx, rate limits, bot blocks) and a
    later attempt may succeed; others are permanent (404, validation, empty
    content) and retrying just wastes resources. We use ``pipeline_attempt`` to
    decide: only requeue rows whose most recent attempt at that stage has a
    transient ``failure_reason`` and whose total attempt count is below
    ``max_attempts``.

    Args:
        max_attempts: Maximum attempts per source per stage before giving up.
            Defaults to ``settings.pipeline_max_attempts``.

    Returns:
        Dict mapping each failure status to the number of rows requeued.
    """
    if max_attempts is None:
        max_attempts = get_settings().pipeline_max_attempts

    # Safe to inline: these are fixed internal constants, never user input.
    transient_list = ",".join(f"'{r}'" for r in sorted(diagnostics.TRANSIENT_REASONS))

    requeued: dict[str, int] = {}
    async with async_session_maker() as session:
        for failed_status, (stage, target_status) in RETRYABLE_FAILURE_RESETS.items():
            result = await session.execute(
                text(f"""
                    UPDATE source_google_news
                    SET status = :target_status, updated_at = CURRENT_TIMESTAMP
                    WHERE status = :failed_status
                    AND (
                        SELECT pa.failure_reason
                        FROM pipeline_attempt pa
                        WHERE pa.source_google_news_id = source_google_news.id
                          AND pa.stage = :stage
                        ORDER BY pa.created_at DESC, pa.id DESC
                        LIMIT 1
                    ) IN ({transient_list})
                    AND (
                        SELECT COUNT(*)
                        FROM pipeline_attempt pa2
                        WHERE pa2.source_google_news_id = source_google_news.id
                          AND pa2.stage = :stage
                    ) < :max_attempts
                """),
                {
                    "target_status": target_status,
                    "failed_status": failed_status,
                    "stage": stage,
                    "max_attempts": max_attempts,
                },
            )
            requeued[failed_status] = result.rowcount or 0
        await session.commit()

    total = sum(requeued.values())
    if total:
        logger.info(f"[RETRY] Requeued {total} transient failures: {requeued}")
    else:
        logger.info("[RETRY] No retryable failures to requeue")

    return requeued


async def merge_exact_duplicate_unique_events(dry_run: bool = True) -> dict:
    """Merge UniqueEvents that share normalized title, city, and calendar date.

    For each duplicate group, keeps the event with the highest ``source_count``
    (ties broken by lowest id), re-links RawEvents, recomputes ``source_count``,
    copies geocoding from losers when the survivor lacks it, and deletes losers.

    Args:
        dry_run: When True, report planned merges without mutating the database.

    Returns:
        Audit dict with groups_found, events_merged, raw_events_relinked, merges.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT id, title, city, event_date, source_count,
                       latitude, longitude, plus_code, place_id,
                       formatted_address, location_precision,
                       geocoding_source, geocoding_confidence
                FROM unique_event
                ORDER BY id
            """)
        )
        rows = [dict(row._mapping) for row in result.fetchall()]

        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = duplicate_group_key(row["title"], row["city"], row["event_date"])
            if key is None:
                continue
            groups.setdefault(key, []).append(row)

        duplicate_groups = [members for members in groups.values() if len(members) > 1]

        audit: dict[str, Any] = {
            "dry_run": dry_run,
            "groups_found": len(duplicate_groups),
            "events_merged": 0,
            "raw_events_relinked": 0,
            "merges": [],
        }

        if not duplicate_groups:
            logger.info("[MERGE] No exact duplicate unique_event groups found")
            return audit

        for members in duplicate_groups:
            survivor_id = pick_survivor_id(members)
            loser_ids = [row["id"] for row in members if row["id"] != survivor_id]
            survivor = next(row for row in members if row["id"] == survivor_id)

            relink_count = 0
            for loser_id in loser_ids:
                count_result = await session.execute(
                    text("""
                        SELECT COUNT(*) AS cnt
                        FROM raw_event
                        WHERE unique_event_id = :loser_id
                    """),
                    {"loser_id": loser_id},
                )
                relink_count += count_result.scalar_one()

            merge_record = {
                "survivor_id": survivor_id,
                "loser_ids": loser_ids,
                "title": survivor["title"],
                "city": survivor["city"],
                "event_date": _event_date_key(survivor["event_date"]),
                "raw_events_relinked": relink_count,
            }
            audit["merges"].append(merge_record)
            audit["events_merged"] += len(loser_ids)
            audit["raw_events_relinked"] += relink_count

            if dry_run:
                continue

            for loser in (row for row in members if row["id"] != survivor_id):
                await session.execute(
                    text("""
                        UPDATE raw_event
                        SET unique_event_id = :survivor_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE unique_event_id = :loser_id
                    """),
                    {"survivor_id": survivor_id, "loser_id": loser["id"]},
                )

                if survivor["latitude"] is None and loser["latitude"] is not None:
                    set_clauses = ", ".join(f"{field} = :{field}" for field in GEOCODING_FIELDS)
                    await session.execute(
                        text(f"""
                            UPDATE unique_event
                            SET {set_clauses},
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :survivor_id
                        """),
                        {field: loser[field] for field in GEOCODING_FIELDS}
                        | {"survivor_id": survivor_id},
                    )
                    for field in GEOCODING_FIELDS:
                        survivor[field] = loser[field]

                await session.execute(
                    text("DELETE FROM unique_event WHERE id = :loser_id"),
                    {"loser_id": loser["id"]},
                )

            count_result = await session.execute(
                text("""
                    SELECT COUNT(*) AS cnt
                    FROM raw_event
                    WHERE unique_event_id = :survivor_id
                """),
                {"survivor_id": survivor_id},
            )
            actual_count = count_result.scalar_one()
            await session.execute(
                text("""
                    UPDATE unique_event
                    SET source_count = :source_count,
                        needs_enrichment = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :survivor_id
                """),
                {"source_count": actual_count, "survivor_id": survivor_id},
            )

        if not dry_run:
            await session.commit()
            logger.info(
                "[MERGE] Merged {events} duplicate events across {groups} groups "
                "({raw} raw_events relinked)",
                events=audit["events_merged"],
                groups=audit["groups_found"],
                raw=audit["raw_events_relinked"],
            )
        else:
            logger.info(
                "[MERGE] Dry-run: would merge {events} events across {groups} groups "
                "({raw} raw_events relinked)",
                events=audit["events_merged"],
                groups=audit["groups_found"],
                raw=audit["raw_events_relinked"],
            )

        return audit
