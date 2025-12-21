"""Public API router for public-facing website."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
import math
import csv
import json
import io

from app.database import get_session
from app.models.unique_event import UniqueEvent

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/stats")
async def get_public_stats(session: AsyncSession = Depends(get_session)):
    """Get public overview stats."""
    
    # Total events
    total = await session.scalar(select(func.count(UniqueEvent.id)))
    
    # Today - based on event_date (use date() function for timezone-safe comparison)
    today_date = datetime.utcnow().date()
    today_query = text("""
        SELECT COUNT(*) 
        FROM unique_event
        WHERE date(event_date) = date(:today_date) 
        AND event_date IS NOT NULL
    """)
    today_result = await session.execute(today_query, {"today_date": today_date.isoformat()})
    today = today_result.scalar()
    
    # This week - based on event_date
    today_datetime = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_datetime - timedelta(days=today_datetime.weekday())
    this_week = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.event_date >= week_start
        ).where(
            UniqueEvent.event_date.isnot(None)
        )
    )
    
    # This month - based on event_date
    month_start = today_datetime.replace(day=1)
    this_month = await session.scalar(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.event_date >= month_start
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
        "today": today or 0,
        "this_week": this_week or 0,
        "this_month": this_month or 0,
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
    format: str = Query("csv", regex="^(csv|json)$"),
    state: str | None = None,
    type: str | None = None,
):
    """Export events as CSV or JSON."""
    
    # Build query
    query = select(UniqueEvent)
    
    if state:
        query = query.where(UniqueEvent.state == state)
    
    if type:
        query = query.where(UniqueEvent.homicide_type == type)
    
    query = query.order_by(UniqueEvent.event_date.desc().nullslast())
    
    result = await session.execute(query)
    events = result.scalars().all()
    
    # Format data
    data = []
    for event in events:
        data.append({
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
    
    if format == "csv":
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
    else:
        # JSON
        json_content = json.dumps(data, ensure_ascii=False, indent=2)
        
        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=eventos.json"}
        )

