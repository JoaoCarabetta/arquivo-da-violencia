"""Stats router for dashboard overview."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_session
from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.models.raw_event import RawEvent
from app.models.unique_event import UniqueEvent

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """Get overview stats for the dashboard."""
    
    # Sources stats
    sources_total = await session.scalar(select(func.count(SourceGoogleNews.id)))
    sources_pending = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(SourceGoogleNews.status == SourceStatus.pending)
    )
    sources_downloaded = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(SourceGoogleNews.status == SourceStatus.downloaded)
    )
    sources_processed = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(SourceGoogleNews.status == SourceStatus.processed)
    )
    sources_failed = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(SourceGoogleNews.status == SourceStatus.failed)
    )
    
    # Raw events stats
    raw_events_total = await session.scalar(select(func.count(RawEvent.id)))
    
    # Unique events stats
    unique_events_total = await session.scalar(select(func.count(UniqueEvent.id)))
    
    return {
        "sources": {
            "total": sources_total or 0,
            "pending": sources_pending or 0,
            "downloaded": sources_downloaded or 0,
            "processed": sources_processed or 0,
            "failed": sources_failed or 0,
        },
        "raw_events": {
            "total": raw_events_total or 0,
        },
        "unique_events": {
            "total": unique_events_total or 0,
        },
    }

