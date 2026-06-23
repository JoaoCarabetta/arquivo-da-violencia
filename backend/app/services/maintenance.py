"""Maintenance helpers for recovering the pipeline from stuck states."""

from loguru import logger

from app.config import get_settings
from app.database import async_session_maker
from app.services import diagnostics


# Map of transient "claimed" statuses back to the queue status they should
# return to if a worker crashed / errored out mid-processing and left the row
# stranded. These intermediate states are only valid while a task is actively
# working a row; anything older than the threshold is safe to requeue.
STUCK_STATUS_RESETS = {
    "classifying": "ready_for_classification",
    "downloading": "ready_for_download",
    "extracting": "ready_for_extraction",
}


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
    from sqlalchemy import text

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
    from sqlalchemy import text

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
