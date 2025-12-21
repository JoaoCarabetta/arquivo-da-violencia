"""Raw Events API router."""

import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import RawEvent, RawEventRead, RawEventUpdate
from app.auth import get_current_user

router = APIRouter(prefix="/raw-events", tags=["raw-events"])


@router.get("", response_model=dict)
async def list_raw_events(
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    homicide_type: str | None = None,
    city: str | None = None,
    state: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    security_force: bool | None = None,
    source_id: int | None = None,
    unique_event_id: int | None = None,
    is_gold_standard: bool | None = None,
):
    """List all raw events with pagination and filtering."""
    # Base query
    query = select(RawEvent)
    count_query = select(func.count(RawEvent.id))
    
    # Apply filters
    if homicide_type:
        query = query.where(RawEvent.homicide_type == homicide_type)
        count_query = count_query.where(RawEvent.homicide_type == homicide_type)
    
    if city:
        query = query.where(RawEvent.city.ilike(f"%{city}%"))
        count_query = count_query.where(RawEvent.city.ilike(f"%{city}%"))
    
    if state:
        query = query.where(RawEvent.state == state)
        count_query = count_query.where(RawEvent.state == state)
    
    if date_from:
        query = query.where(RawEvent.event_date >= date_from)
        count_query = count_query.where(RawEvent.event_date >= date_from)
    
    if date_to:
        query = query.where(RawEvent.event_date <= date_to)
        count_query = count_query.where(RawEvent.event_date <= date_to)
    
    if security_force is not None:
        query = query.where(RawEvent.security_force_involved == security_force)
        count_query = count_query.where(RawEvent.security_force_involved == security_force)
    
    if source_id:
        query = query.where(RawEvent.source_google_news_id == source_id)
        count_query = count_query.where(RawEvent.source_google_news_id == source_id)
    
    if unique_event_id:
        query = query.where(RawEvent.unique_event_id == unique_event_id)
        count_query = count_query.where(RawEvent.unique_event_id == unique_event_id)
    
    if is_gold_standard is not None:
        query = query.where(RawEvent.is_gold_standard == is_gold_standard)
        count_query = count_query.where(RawEvent.is_gold_standard == is_gold_standard)
    
    # Get total count
    total = await session.exec(count_query)
    total_count = total.one()
    
    # Calculate pagination
    skip = (page - 1) * per_page
    pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    
    # Apply pagination and ordering
    query = query.order_by(RawEvent.created_at.desc())
    query = query.offset(skip).limit(per_page)
    
    result = await session.exec(query)
    events = result.all()
    
    return {
        "items": [RawEventRead.model_validate(e) for e in events],
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/{event_id}", response_model=RawEventRead)
async def get_raw_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single raw event by ID."""
    event = await session.get(RawEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Raw event not found")
    return event


@router.get("/{event_id}/extraction", response_model=dict)
async def get_raw_event_extraction(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get the full extraction data for a raw event."""
    event = await session.get(RawEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Raw event not found")
    
    return {
        "id": event.id,
        "extraction_model": event.extraction_model,
        "extraction_success": event.extraction_success,
        "extraction_error": event.extraction_error,
        "extraction_data": event.extraction_data,
    }


@router.patch("/{event_id}", response_model=RawEventRead)
async def update_raw_event(
    event_id: int,
    event_update: RawEventUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    """Update extraction_data and/or is_gold_standard flag."""
    # Get the event
    event = await session.get(RawEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Raw event not found")
    
    # Update fields if provided
    if event_update.extraction_data is not None:
        event.extraction_data = event_update.extraction_data
    
    if event_update.is_gold_standard is not None:
        event.is_gold_standard = event_update.is_gold_standard
    
    # Save changes
    session.add(event)
    await session.commit()
    await session.refresh(event)
    
    return event


@router.get("/stats/summary", response_model=dict)
async def get_raw_events_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get summary statistics for raw events."""
    # Total count
    total_query = select(func.count(RawEvent.id))
    total_result = await session.exec(total_query)
    total = total_result.one()
    
    # Count by homicide type
    type_query = select(
        RawEvent.homicide_type,
        func.count(RawEvent.id)
    ).where(RawEvent.homicide_type.isnot(None)).group_by(RawEvent.homicide_type)
    
    type_result = await session.exec(type_query)
    by_type = {row[0]: row[1] for row in type_result.all()}
    
    # Count by city
    city_query = select(
        RawEvent.city,
        func.count(RawEvent.id)
    ).where(RawEvent.city.isnot(None)).group_by(RawEvent.city).limit(10)
    
    city_result = await session.exec(city_query)
    by_city = {row[0]: row[1] for row in city_result.all()}
    
    # Security force involvement
    sf_query = select(func.count(RawEvent.id)).where(
        RawEvent.security_force_involved == True  # noqa: E712
    )
    sf_result = await session.exec(sf_query)
    security_force_count = sf_result.one()
    
    return {
        "total": total,
        "by_homicide_type": by_type,
        "by_city": by_city,
        "security_force_involved": security_force_count,
    }
