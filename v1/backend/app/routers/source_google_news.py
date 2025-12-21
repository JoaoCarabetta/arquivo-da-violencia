"""Google News Sources API router."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text
import math

from app.database import get_session
from app.models import SourceGoogleNews, SourceGoogleNewsRead, SourceStatus

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=dict)
async def list_sources(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: SourceStatus | None = None,
    search: str | None = None,
):
    """List all Google News sources with pagination and filtering."""
    # Base query
    query = select(SourceGoogleNews)
    count_query = select(func.count(SourceGoogleNews.id))
    
    # Apply filters
    if status:
        query = query.where(SourceGoogleNews.status == status)
        count_query = count_query.where(SourceGoogleNews.status == status)
    
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            SourceGoogleNews.headline.ilike(search_filter) |
            SourceGoogleNews.publisher_name.ilike(search_filter)
        )
        count_query = count_query.where(
            SourceGoogleNews.headline.ilike(search_filter) |
            SourceGoogleNews.publisher_name.ilike(search_filter)
        )
    
    # Get total count
    total = await session.exec(count_query)
    total_count = total.one()
    
    # Calculate pagination
    skip = (page - 1) * per_page
    pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    
    # Apply pagination and ordering
    query = query.order_by(SourceGoogleNews.fetched_at.desc())
    query = query.offset(skip).limit(per_page)
    
    result = await session.exec(query)
    sources = result.all()
    
    return {
        "items": [SourceGoogleNewsRead.model_validate(s) for s in sources],
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/{source_id}", response_model=SourceGoogleNewsRead)
async def get_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single source by ID."""
    source = await session.get(SourceGoogleNews, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.get("/stats/summary", response_model=dict)
async def get_sources_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get summary statistics for sources."""
    # Count by status
    status_query = select(
        SourceGoogleNews.status,
        func.count(SourceGoogleNews.id)
    ).group_by(SourceGoogleNews.status)
    
    result = await session.exec(status_query)
    status_counts = {row[0]: row[1] for row in result.all()}
    
    # Total count
    total_query = select(func.count(SourceGoogleNews.id))
    total_result = await session.exec(total_query)
    total = total_result.one()
    
    return {
        "total": total,
        "by_status": status_counts,
    }


@router.get("/stats/by-hour", response_model=dict)
async def get_sources_by_hour(
    session: AsyncSession = Depends(get_session),
    hours: int = Query(24, ge=1, le=168),  # Default 24 hours, max 7 days
):
    """Get sources grouped by hour for the last N hours."""
    # Calculate the cutoff time
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Use raw SQL to group by hour (SQLite uses strftime)
    query = text("""
        SELECT 
            strftime('%Y-%m-%d %H:00:00', fetched_at) as hour,
            COUNT(*) as count
        FROM source_google_news
        WHERE fetched_at >= :cutoff_time
        GROUP BY hour
        ORDER BY hour ASC
    """)
    
    result = await session.execute(query, {"cutoff_time": cutoff_time})
    rows = result.fetchall()
    
    # Format the data
    chart_data = []
    for row in rows:
        chart_data.append({
            "hour": row[0],
            "count": row[1],
        })
    
    return {
        "data": chart_data,
        "hours": hours,
    }
