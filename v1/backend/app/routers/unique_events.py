"""Unique Events API router."""

import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import UniqueEvent, UniqueEventRead

router = APIRouter(prefix="/unique-events", tags=["unique-events"])


@router.get("", response_model=dict)
async def list_unique_events(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    homicide_type: str | None = None,
    city: str | None = None,
    state: str | None = None,
    neighborhood: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    security_force: bool | None = None,
    confirmed: bool | None = None,
    has_geolocation: bool | None = None,
    search: str | None = None,
):
    """List all unique events with pagination and filtering."""
    # Base query
    query = select(UniqueEvent)
    count_query = select(func.count(UniqueEvent.id))
    
    # Apply filters
    if homicide_type:
        query = query.where(UniqueEvent.homicide_type == homicide_type)
        count_query = count_query.where(UniqueEvent.homicide_type == homicide_type)
    
    if city:
        query = query.where(UniqueEvent.city.ilike(f"%{city}%"))
        count_query = count_query.where(UniqueEvent.city.ilike(f"%{city}%"))
    
    if state:
        query = query.where(UniqueEvent.state == state)
        count_query = count_query.where(UniqueEvent.state == state)
    
    if neighborhood:
        query = query.where(UniqueEvent.neighborhood.ilike(f"%{neighborhood}%"))
        count_query = count_query.where(UniqueEvent.neighborhood.ilike(f"%{neighborhood}%"))
    
    if date_from:
        query = query.where(UniqueEvent.event_date >= date_from)
        count_query = count_query.where(UniqueEvent.event_date >= date_from)
    
    if date_to:
        query = query.where(UniqueEvent.event_date <= date_to)
        count_query = count_query.where(UniqueEvent.event_date <= date_to)
    
    if security_force is not None:
        query = query.where(UniqueEvent.security_force_involved == security_force)
        count_query = count_query.where(UniqueEvent.security_force_involved == security_force)
    
    if confirmed is not None:
        query = query.where(UniqueEvent.confirmed == confirmed)
        count_query = count_query.where(UniqueEvent.confirmed == confirmed)
    
    if has_geolocation is not None:
        if has_geolocation:
            query = query.where(UniqueEvent.latitude.isnot(None))
            count_query = count_query.where(UniqueEvent.latitude.isnot(None))
        else:
            query = query.where(UniqueEvent.latitude.is_(None))
            count_query = count_query.where(UniqueEvent.latitude.is_(None))
    
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            UniqueEvent.title.ilike(search_filter) |
            UniqueEvent.chronological_description.ilike(search_filter) |
            UniqueEvent.victims_summary.ilike(search_filter)
        )
        count_query = count_query.where(
            UniqueEvent.title.ilike(search_filter) |
            UniqueEvent.chronological_description.ilike(search_filter) |
            UniqueEvent.victims_summary.ilike(search_filter)
        )
    
    # Get total count
    total = await session.exec(count_query)
    total_count = total.one()
    
    # Calculate pagination
    skip = (page - 1) * per_page
    pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    
    # Apply pagination and ordering
    query = query.order_by(UniqueEvent.event_date.desc().nullslast())
    query = query.offset(skip).limit(per_page)
    
    result = await session.exec(query)
    events = result.all()
    
    return {
        "items": [UniqueEventRead.model_validate(e) for e in events],
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/map", response_model=list)
async def get_events_for_map(
    session: AsyncSession = Depends(get_session),
    date_from: date | None = None,
    date_to: date | None = None,
    homicide_type: str | None = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    """Get events with geolocation for map display."""
    query = select(
        UniqueEvent.id,
        UniqueEvent.title,
        UniqueEvent.event_date,
        UniqueEvent.homicide_type,
        UniqueEvent.latitude,
        UniqueEvent.longitude,
        UniqueEvent.victim_count,
        UniqueEvent.neighborhood,
        UniqueEvent.city,
    ).where(UniqueEvent.latitude.isnot(None))
    
    if date_from:
        query = query.where(UniqueEvent.event_date >= date_from)
    if date_to:
        query = query.where(UniqueEvent.event_date <= date_to)
    if homicide_type:
        query = query.where(UniqueEvent.homicide_type == homicide_type)
    
    query = query.order_by(UniqueEvent.event_date.desc().nullslast()).limit(limit)
    
    result = await session.exec(query)
    events = result.all()
    
    return [
        {
            "id": e.id,
            "title": e.title,
            "event_date": e.event_date.isoformat() if e.event_date else None,
            "homicide_type": e.homicide_type,
            "latitude": float(e.latitude) if e.latitude else None,
            "longitude": float(e.longitude) if e.longitude else None,
            "victim_count": e.victim_count,
            "neighborhood": e.neighborhood,
            "city": e.city,
        }
        for e in events
    ]


@router.get("/{event_id}", response_model=UniqueEventRead)
async def get_unique_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single unique event by ID."""
    event = await session.get(UniqueEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Unique event not found")
    return event


@router.get("/{event_id}/merged-data", response_model=dict)
async def get_unique_event_merged_data(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get the full merged data for a unique event."""
    event = await session.get(UniqueEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Unique event not found")
    
    return {
        "id": event.id,
        "source_count": event.source_count,
        "merged_data": event.merged_data,
    }


@router.get("/stats/summary", response_model=dict)
async def get_unique_events_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get summary statistics for unique events."""
    # Total count
    total_query = select(func.count(UniqueEvent.id))
    total_result = await session.exec(total_query)
    total = total_result.one()
    
    # Count by homicide type
    type_query = select(
        UniqueEvent.homicide_type,
        func.count(UniqueEvent.id)
    ).where(UniqueEvent.homicide_type.isnot(None)).group_by(UniqueEvent.homicide_type)
    
    type_result = await session.exec(type_query)
    by_type = {row[0]: row[1] for row in type_result.all()}
    
    # Total victims
    victims_query = select(func.sum(UniqueEvent.victim_count))
    victims_result = await session.exec(victims_query)
    total_victims = victims_result.one() or 0
    
    # Geocoded count
    geo_query = select(func.count(UniqueEvent.id)).where(
        UniqueEvent.latitude.isnot(None)
    )
    geo_result = await session.exec(geo_query)
    geocoded = geo_result.one()
    
    # Confirmed count
    confirmed_query = select(func.count(UniqueEvent.id)).where(
        UniqueEvent.confirmed == True  # noqa: E712
    )
    confirmed_result = await session.exec(confirmed_query)
    confirmed = confirmed_result.one()
    
    # Security force involvement
    sf_query = select(func.count(UniqueEvent.id)).where(
        UniqueEvent.security_force_involved == True  # noqa: E712
    )
    sf_result = await session.exec(sf_query)
    security_force_count = sf_result.one()
    
    return {
        "total": total,
        "total_victims": total_victims,
        "by_homicide_type": by_type,
        "geocoded": geocoded,
        "confirmed": confirmed,
        "security_force_involved": security_force_count,
    }


@router.get("/stats/by-date", response_model=list)
async def get_events_by_date(
    session: AsyncSession = Depends(get_session),
    days: int = Query(30, ge=1, le=365),
):
    """Get victim count by date for charts."""
    from datetime import datetime, timedelta
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    query = select(
        func.date(UniqueEvent.event_date),
        func.sum(UniqueEvent.victim_count)
    ).where(
        UniqueEvent.event_date >= start_date,
        UniqueEvent.event_date <= end_date,
        UniqueEvent.victim_count.isnot(None)
    ).group_by(
        func.date(UniqueEvent.event_date)
    ).order_by(
        func.date(UniqueEvent.event_date)
    )
    
    result = await session.exec(query)
    data = result.all()
    
    # Fill in missing dates with 0
    date_map = {row[0]: row[1] for row in data}
    full_data = []
    current_date = start_date.date()
    while current_date <= end_date.date():
        date_str = current_date.isoformat()
        full_data.append({
            "date": date_str,
            "victims": date_map.get(date_str, 0) or 0,
        })
        current_date += timedelta(days=1)
    
    return full_data
