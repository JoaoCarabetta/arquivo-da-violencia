"""Poll Postgres and expose pipeline inventory gauges for Grafana."""

from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import func, select, text

from app.database import async_session_maker
from app.metrics import set_pipeline_inventory_metrics
from app.models.pipeline_attempt import PipelineAttempt
from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews
from app.models.unique_event import UniqueEvent

STUCK_STATUSES = ("classifying", "downloading", "extracting")
STUCK_MINUTES = 15
FAILURE_WINDOW_HOURS = 24


async def refresh_pipeline_inventory_metrics() -> None:
    """Load source counts, stuck items, and recent failures from Postgres."""
    try:
        async with async_session_maker() as session:
            status_rows = (
                await session.execute(
                    select(SourceGoogleNews.status, func.count(SourceGoogleNews.id)).group_by(
                        SourceGoogleNews.status
                    )
                )
            ).all()
            status_counts = {str(status): int(count) for status, count in status_rows}

            stuck_cutoff = datetime.utcnow() - timedelta(minutes=STUCK_MINUTES)
            stuck_rows = (
                await session.execute(
                    text(
                        """
                        SELECT status, COUNT(*)
                        FROM source_google_news
                        WHERE status IN ('classifying', 'downloading', 'extracting')
                          AND updated_at < :cutoff
                        GROUP BY status
                        """
                    ),
                    {"cutoff": stuck_cutoff},
                )
            ).all()
            stuck_counts = {str(status): int(count) for status, count in stuck_rows}

            failure_cutoff = datetime.utcnow() - timedelta(hours=FAILURE_WINDOW_HOURS)
            failure_rows = (
                await session.execute(
                    select(
                        PipelineAttempt.stage,
                        PipelineAttempt.failure_reason,
                        func.count(PipelineAttempt.id),
                    )
                    .where(
                        PipelineAttempt.outcome == "failure",
                        PipelineAttempt.created_at >= failure_cutoff,
                        PipelineAttempt.failure_reason.is_not(None),
                    )
                    .group_by(PipelineAttempt.stage, PipelineAttempt.failure_reason)
                )
            ).all()
            failure_counts = {
                (str(stage), str(reason)): int(count)
                for stage, reason, count in failure_rows
            }

            discard_rows = (
                await session.execute(
                    select(
                        PipelineAttempt.stage,
                        PipelineAttempt.failure_reason,
                        func.count(PipelineAttempt.id),
                    )
                    .where(
                        PipelineAttempt.outcome == "discarded",
                        PipelineAttempt.created_at >= failure_cutoff,
                        PipelineAttempt.failure_reason.is_not(None),
                    )
                    .group_by(PipelineAttempt.stage, PipelineAttempt.failure_reason)
                )
            ).all()
            discard_counts = {
                (str(stage), str(reason)): int(count)
                for stage, reason, count in discard_rows
            }

            sources_total = await session.scalar(select(func.count(SourceGoogleNews.id)))
            violent_death = await session.scalar(
                select(func.count(SourceGoogleNews.id)).where(
                    SourceGoogleNews.is_violent_death.is_(True)
                )
            )
            raw_events_total = await session.scalar(select(func.count(RawEvent.id)))
            unique_events_total = await session.scalar(select(func.count(UniqueEvent.id)))

        set_pipeline_inventory_metrics(
            status_counts=status_counts,
            stuck_counts={status: stuck_counts.get(status, 0) for status in STUCK_STATUSES},
            failure_counts=failure_counts,
            discard_counts=discard_counts,
            sources_total=int(sources_total or 0),
            violent_death=int(violent_death or 0),
            raw_events_total=int(raw_events_total or 0),
            unique_events_total=int(unique_events_total or 0),
        )
    except Exception as e:
        logger.error(f"[PipelineInventory] Failed to refresh metrics: {e}")
