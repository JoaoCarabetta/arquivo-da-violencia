"""Stats router for dashboard overview."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_session
from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.models.raw_event import RawEvent
from app.models.unique_event import UniqueEvent
from app.auth import require_admin

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_admin)
):
    """Get overview stats for the dashboard."""
    
    # Sources stats by new status names
    sources_total = await session.scalar(select(func.count(SourceGoogleNews.id)))
    
    sources_ready_for_classification = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.ready_for_classification
        )
    )
    sources_discarded = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.discarded
        )
    )
    sources_ready_for_download = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.ready_for_download
        )
    )
    sources_ready_for_extraction = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.ready_for_extraction
        )
    )
    sources_extracted = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.extracted
        )
    )
    sources_failed_in_download = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.failed_in_download
        )
    )
    sources_failed_in_extraction = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.status == SourceStatus.failed_in_extraction
        )
    )
    
    # Classification stats
    sources_violent_death = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.is_violent_death == True
        )
    )
    sources_not_violent_death = await session.scalar(
        select(func.count(SourceGoogleNews.id)).where(
            SourceGoogleNews.is_violent_death == False
        )
    )
    
    # Raw events stats
    raw_events_total = await session.scalar(select(func.count(RawEvent.id)))
    
    # Unique events stats
    unique_events_total = await session.scalar(select(func.count(UniqueEvent.id)))
    
    return {
        "sources": {
            "total": sources_total or 0,
            "ready_for_classification": sources_ready_for_classification or 0,
            "discarded": sources_discarded or 0,
            "ready_for_download": sources_ready_for_download or 0,
            "ready_for_extraction": sources_ready_for_extraction or 0,
            "extracted": sources_extracted or 0,
            "failed_in_download": sources_failed_in_download or 0,
            "failed_in_extraction": sources_failed_in_extraction or 0,
        },
        "classification": {
            "violent_death": sources_violent_death or 0,
            "not_violent_death": sources_not_violent_death or 0,
        },
        "raw_events": {
            "total": raw_events_total or 0,
        },
        "unique_events": {
            "total": unique_events_total or 0,
        },
    }

