"""Maintenance helpers for recovering the pipeline from stuck states."""

from loguru import logger

from app.database import async_session_maker


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
