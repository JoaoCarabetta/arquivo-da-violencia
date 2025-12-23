"""Public API router for public-facing website."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
import math
import csv
import json  # For serializing merged_data
import io

from app.database import get_session
from app.models.unique_event import UniqueEvent
from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/stats")
async def get_public_stats(session: AsyncSession = Depends(get_session)):
    """Get public overview stats."""
    
    # Total events
    total = await session.scalar(select(func.count(UniqueEvent.id)))
    
    # Current datetime for rolling window calculations
    now = datetime.utcnow()
    
    # Last 7 days - events from 7 days ago to now (exclude future events)
    last_7_days_start = now - timedelta(days=7)
    last_7_days = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.event_date >= last_7_days_start
        ).where(
            UniqueEvent.event_date <= now
        ).where(
            UniqueEvent.event_date.isnot(None)
        )
    )
    
    # Last 30 days - events from 30 days ago to now (exclude future events)
    last_30_days_start = now - timedelta(days=30)
    last_30_days = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.event_date >= last_30_days_start
        ).where(
            UniqueEvent.event_date <= now
        ).where(
            UniqueEvent.event_date.isnot(None)
        )
    )
    
    # Project start date - use earliest event_date, fallback to 2025-12-21 if none
    earliest = await session.scalar(
        select(func.min(UniqueEvent.event_date))
    )
    
    # Default to 2025-12-21 if no events found, otherwise use earliest event_date
    if earliest:
        # Convert to date if it's a datetime
        if isinstance(earliest, datetime):
            since_date = earliest.date()
        else:
            since_date = earliest
    else:
        since_date = datetime(2025, 12, 21).date()
    
    return {
        "total": total or 0,
        "last_7_days": last_7_days or 0,
        "last_30_days": last_30_days or 0,
        "since": since_date.isoformat()
    }


@router.get("/stats/by-type")
async def get_stats_by_type(session: AsyncSession = Depends(get_session)):
    """Get event counts by homicide type."""
    
    query = select(
        UniqueEvent.homicide_type,
        func.count(UniqueEvent.id).label('count')
    ).group_by(UniqueEvent.homicide_type)
    
    result = await session.execute(query)
    rows = result.all()
    
    # Calculate total for percentages
    total = sum(row.count for row in rows)
    
    data = []
    for row in rows:
        type_name = row.homicide_type or "Não classificado"
        count = row.count
        percent = (count / total * 100) if total > 0 else 0
        data.append({
            "type": type_name,
            "count": count,
            "percent": round(percent, 1)
        })
    
    # Sort by count descending
    data.sort(key=lambda x: x['count'], reverse=True)
    
    return data


@router.get("/stats/by-state")
async def get_stats_by_state(session: AsyncSession = Depends(get_session)):
    """Get event counts by state."""
    
    query = select(
        UniqueEvent.state,
        func.count(UniqueEvent.id).label('count')
    ).where(
        UniqueEvent.state.isnot(None)
    ).group_by(UniqueEvent.state).order_by(func.count(UniqueEvent.id).desc())
    
    result = await session.execute(query)
    rows = result.all()
    
    data = []
    for row in rows:
        data.append({
            "state": row.state,
            "count": row.count
        })
    
    return data


@router.get("/stats/by-day")
async def get_stats_by_day(
    session: AsyncSession = Depends(get_session),
    days: int = Query(30, ge=1, le=365)
):
    """Get daily event counts."""
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Use SQLite date function with event_date instead of created_at
    query = text("""
        SELECT 
            date(event_date) as date,
            COUNT(*) as count
        FROM unique_event
        WHERE event_date >= :cutoff AND event_date IS NOT NULL
        GROUP BY date
        ORDER BY date ASC
    """)
    
    result = await session.execute(query, {"cutoff": cutoff})
    rows = result.fetchall()
    
    data = []
    for row in rows:
        data.append({
            "date": row[0],
            "count": row[1]
        })
    
    return data


@router.get("/stats/security-force")
async def get_security_force_stats(session: AsyncSession = Depends(get_session)):
    """Get counts of events with/without security force involvement."""
    
    involved = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.security_force_involved == True
        )
    )
    
    not_involved = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.security_force_involved == False
        )
    )
    
    unknown = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.security_force_involved.is_(None)
        )
    )
    
    return {
        "involved": involved or 0,
        "not_involved": not_involved or 0,
        "unknown": unknown or 0
    }


@router.get("/events")
async def get_public_events(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    state: str | None = None,
    type: str | None = None,
    search: str | None = None,
):
    """Get paginated public events."""
    
    # Base query
    query = select(UniqueEvent)
    count_query = select(func.count(UniqueEvent.id))
    
    # Apply filters
    if state:
        query = query.where(UniqueEvent.state == state)
        count_query = count_query.where(UniqueEvent.state == state)
    
    if type:
        query = query.where(UniqueEvent.homicide_type == type)
        count_query = count_query.where(UniqueEvent.homicide_type == type)
    
    if search:
        search_filter = f"%{search}%"
        search_condition = (
            UniqueEvent.title.ilike(search_filter) |
            UniqueEvent.city.ilike(search_filter) |
            UniqueEvent.chronological_description.ilike(search_filter)
        )
        query = query.where(search_condition)
        count_query = count_query.where(search_condition)
    
    # Get total count
    total = await session.scalar(count_query)
    total_count = total or 0
    
    # Calculate pagination
    skip = (page - 1) * per_page
    pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    
    # Apply pagination and ordering by event_date (most recent first, nulls last)
    query = query.order_by(UniqueEvent.event_date.desc().nullslast())
    query = query.offset(skip).limit(per_page)
    
    result = await session.execute(query)
    events = result.scalars().all()
    
    # Format events for public consumption (exclude sensitive fields)
    items = []
    for event in events:
        items.append({
            "id": event.id,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "time_of_day": event.time_of_day,
            "state": event.state,
            "city": event.city,
            "neighborhood": event.neighborhood,
            "homicide_type": event.homicide_type,
            "method_of_death": event.method_of_death,
            "victim_count": event.victim_count,
            "victims_summary": event.victims_summary,
            "security_force_involved": event.security_force_involved,
            "title": event.title,
            "chronological_description": event.chronological_description,
            "latitude": float(event.latitude) if event.latitude else None,
            "longitude": float(event.longitude) if event.longitude else None,
            "source_count": event.source_count,
            "merged_data": event.merged_data,
            "created_at": event.created_at.isoformat(),
        })
    
    return {
        "items": items,
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/events/export")
async def export_events(
    session: AsyncSession = Depends(get_session),
    state: str | None = None,
    type: str | None = None,
):
    """Export all unique events as CSV with complete data."""
    
    # Build query - get ALL unique events
    query = select(UniqueEvent)
    
    if state:
        query = query.where(UniqueEvent.state == state)
    
    if type:
        query = query.where(UniqueEvent.homicide_type == type)
    
    query = query.order_by(UniqueEvent.event_date.desc().nullslast())
    
    result = await session.execute(query)
    events = result.scalars().all()
    
    # Format data with ALL fields from UniqueEvent
    data = []
    for event in events:
        # Serialize merged_data as JSON string if present
        merged_data_str = None
        if event.merged_data:
            merged_data_str = json.dumps(event.merged_data, ensure_ascii=False)
        
        data.append({
            "id": event.id,
            "homicide_type": event.homicide_type,
            "method_of_death": event.method_of_death,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "date_precision": event.date_precision,
            "time_of_day": event.time_of_day,
            "country": event.country,
            "state": event.state,
            "city": event.city,
            "neighborhood": event.neighborhood,
            "street": event.street,
            "establishment": event.establishment,
            "full_location_description": event.full_location_description,
            "latitude": float(event.latitude) if event.latitude else None,
            "longitude": float(event.longitude) if event.longitude else None,
            "plus_code": event.plus_code,
            "place_id": event.place_id,
            "formatted_address": event.formatted_address,
            "location_precision": event.location_precision,
            "geocoding_source": event.geocoding_source,
            "geocoding_confidence": event.geocoding_confidence,
            "victim_count": event.victim_count,
            "identified_victim_count": event.identified_victim_count,
            "victims_summary": event.victims_summary,
            "perpetrator_count": event.perpetrator_count,
            "identified_perpetrator_count": event.identified_perpetrator_count,
            "security_force_involved": event.security_force_involved,
            "title": event.title,
            "chronological_description": event.chronological_description,
            "additional_context": event.additional_context,
            "merged_data": merged_data_str,
            "source_count": event.source_count,
            "confirmed": event.confirmed,
            "needs_enrichment": event.needs_enrichment,
            "last_enriched_at": event.last_enriched_at.isoformat() if event.last_enriched_at else None,
            "enrichment_model": event.enrichment_model,
            "created_at": event.created_at.isoformat(),
            "updated_at": event.updated_at.isoformat(),
        })
    
    # Create CSV
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    
    csv_content = output.getvalue()
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eventos.csv"}
    )


@router.get("/events/{event_id}")
async def get_public_event_by_id(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single public event by ID with all related sources."""
    
    # Fetch the unique event
    event = await session.get(UniqueEvent, event_id)
    if not event:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Fetch all raw events linked to this unique event
    raw_events_query = select(RawEvent).where(RawEvent.unique_event_id == event_id)
    raw_events_result = await session.execute(raw_events_query)
    raw_events = raw_events_result.scalars().all()
    
    # Get all source IDs from raw events
    source_ids = [re.source_google_news_id for re in raw_events if re.source_google_news_id]
    
    # Fetch all sources
    sources = []
    if source_ids:
        sources_query = select(SourceGoogleNews).where(SourceGoogleNews.id.in_(source_ids))
        sources_result = await session.execute(sources_query)
        sources_list = sources_result.scalars().all()
        
        # Format sources for response
        for source in sources_list:
            sources.append({
                "id": source.id,
                "headline": source.headline,
                "publisher_name": source.publisher_name,
                "url": source.resolved_url or source.google_news_url,
                "published_at": source.published_at.isoformat() if source.published_at else None,
            })
    
    # Format event for public consumption
    event_data = {
        "id": event.id,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "time_of_day": event.time_of_day,
        "state": event.state,
        "city": event.city,
        "neighborhood": event.neighborhood,
        "homicide_type": event.homicide_type,
        "method_of_death": event.method_of_death,
        "victim_count": event.victim_count,
        "victims_summary": event.victims_summary,
        "security_force_involved": event.security_force_involved,
        "title": event.title,
        "chronological_description": event.chronological_description,
        "latitude": float(event.latitude) if event.latitude else None,
        "longitude": float(event.longitude) if event.longitude else None,
        "formatted_address": event.formatted_address,
        "source_count": event.source_count,
        "merged_data": event.merged_data,
        "created_at": event.created_at.isoformat(),
        "sources": sources,
    }
    
    return event_data

