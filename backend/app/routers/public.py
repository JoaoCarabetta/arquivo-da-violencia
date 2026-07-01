"""Public API router for public-facing website."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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

# Rolling window shared by the map, export, and temporal-scope note.
PUBLIC_MAP_DAYS = 365

EXPORT_FIELD_NAMES = [
    "id",
    "homicide_type",
    "method_of_death",
    "event_date",
    "date_precision",
    "time_of_day",
    "country",
    "state",
    "city",
    "neighborhood",
    "street",
    "establishment",
    "full_location_description",
    "latitude",
    "longitude",
    "plus_code",
    "place_id",
    "formatted_address",
    "location_precision",
    "geocoding_source",
    "geocoding_confidence",
    "victim_count",
    "identified_victim_count",
    "victims_summary",
    "perpetrator_count",
    "identified_perpetrator_count",
    "security_force_involved",
    "title",
    "chronological_description",
    "additional_context",
    "merged_data",
    "source_count",
    "confirmed",
    "needs_enrichment",
    "last_enriched_at",
    "enrichment_model",
    "created_at",
    "updated_at",
]


def _map_window(days: int = PUBLIC_MAP_DAYS) -> tuple[datetime, datetime]:
    """Return (cutoff, now) for the public map data window."""
    now = datetime.utcnow()
    return now - timedelta(days=days), now


def _expand_period_filters(periods: list[str]) -> list[str]:
    """Match period filters across spelling variants (e.g. manhã / manha)."""
    expanded: set[str] = set()
    for period in periods:
        if period.lower() in ("manhã", "manha"):
            expanded.update(["manhã", "manha"])
        else:
            expanded.add(period)
    return list(expanded)


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
    
    # Earliest event in the public map window (geocoded, last 365 days).
    cutoff, now = _map_window(PUBLIC_MAP_DAYS)
    earliest = await session.scalar(
        select(func.min(UniqueEvent.event_date)).where(
            UniqueEvent.event_date >= cutoff,
            UniqueEvent.event_date <= now,
            UniqueEvent.event_date.isnot(None),
            UniqueEvent.latitude.isnot(None),
            UniqueEvent.longitude.isnot(None),
        )
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


@router.get("/geocode")
async def geocode_location(
    request: Request,
    q: str | None = Query(None, description="Free-text place (city, neighborhood, address)"),
    cep: str | None = Query(None, description="Brazilian postal code (CEP)"),
):
    """
    Resolve a user-supplied location (CEP, city or neighborhood) to coordinates.

    Used by the homepage "near me" search. The browser sends the typed text and
    gets back lat/lng so it can then call /nearby. Geolocation (GPS) skips this.
    """
    from app.services.geocoding import geocode_user_query
    from app.services.geocode_protection import (
        cache_geocode_response,
        enforce_geocode_rate_limit,
        get_cached_geocode,
        get_client_ip,
        log_geocode_request,
        normalize_geocode_query,
    )

    query = (cep or q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Informe um CEP, cidade ou bairro")

    client_ip = get_client_ip(request)
    normalized = normalize_geocode_query(query)

    cached = await get_cached_geocode(normalized)
    if cached is not None:
        log_geocode_request(client_ip=client_ip, query=query, cache_hit=True)
        return cached

    await enforce_geocode_rate_limit(client_ip)
    log_geocode_request(client_ip=client_ip, query=query, cache_hit=False)

    result = await geocode_user_query(query)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Não foi possível localizar esse endereço",
        )

    payload = {
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "label": result["label"],
        "source": result["source"],
        "query": query,
        "zoom": result.get("zoom"),
    }
    await cache_geocode_response(normalized, payload)
    return payload


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


@router.get("/nearby")
async def get_nearby_events(
    session: AsyncSession = Depends(get_session),
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_km: float = Query(5.0, gt=0, le=200, description="Search radius in km"),
    days: int | None = Query(None, ge=1, le=3650, description="Only events in the last N days"),
    limit: int = Query(100, ge=1, le=500, description="Max events returned"),
):
    """
    Return geocoded violent-death events near a point, plus a "most common
    crimes near you" summary (counts by type, by method, security-force share,
    and the trend vs the previous equal period).

    SQLite has no geo functions, so we prefilter with a lat/lng bounding box in
    SQL and then compute the exact Haversine distance in Python.
    """
    # Bounding box (degrees). 1 deg latitude ~= 111 km; longitude shrinks with
    # latitude. cos can be ~0 near the poles, so clamp to avoid huge boxes.
    lat_delta = radius_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lng_delta = radius_km / (111.0 * cos_lat)

    min_lat, max_lat = lat - lat_delta, lat + lat_delta
    min_lng, max_lng = lng - lng_delta, lng + lng_delta

    query = select(UniqueEvent).where(
        UniqueEvent.latitude.isnot(None),
        UniqueEvent.longitude.isnot(None),
        UniqueEvent.latitude >= min_lat,
        UniqueEvent.latitude <= max_lat,
        UniqueEvent.longitude >= min_lng,
        UniqueEvent.longitude <= max_lng,
    )

    now = datetime.utcnow()
    cutoff = None
    prev_cutoff = None
    if days is not None:
        cutoff = now - timedelta(days=days)
        prev_cutoff = now - timedelta(days=days * 2)
        # Keep events older than the window too (for trend); filter per-bucket below.
        query = query.where(
            (UniqueEvent.event_date >= prev_cutoff) | (UniqueEvent.event_date.is_(None))
        )

    result = await session.execute(query)
    candidates = result.scalars().all()

    # Exact distance filter + distance annotation.
    in_radius = []
    for event in candidates:
        try:
            elat = float(event.latitude)
            elng = float(event.longitude)
        except (TypeError, ValueError):
            continue
        distance = _haversine_km(lat, lng, elat, elng)
        if distance <= radius_km:
            in_radius.append((distance, event))

    # Split into current vs previous period for the trend (only when days given).
    def in_current_period(ev) -> bool:
        if cutoff is None:
            return True
        return ev.event_date is not None and ev.event_date >= cutoff

    def in_previous_period(ev) -> bool:
        if cutoff is None or prev_cutoff is None:
            return False
        return ev.event_date is not None and prev_cutoff <= ev.event_date < cutoff

    current = [(d, e) for d, e in in_radius if in_current_period(e)]
    previous_count = sum(1 for _, e in in_radius if in_previous_period(e))

    # Aggregations over the current-period events.
    by_type: dict[str, int] = {}
    by_method: dict[str, int] = {}
    security_involved = 0
    total_victims = 0
    for _, event in current:
        t = event.homicide_type or "Não classificado"
        by_type[t] = by_type.get(t, 0) + 1
        m = event.method_of_death or "Não especificado"
        by_method[m] = by_method.get(m, 0) + 1
        if event.security_force_involved:
            security_involved += 1
        if event.victim_count:
            total_victims += event.victim_count

    def to_sorted(d: dict[str, int]) -> list[dict]:
        total = sum(d.values()) or 1
        items = [
            {"label": k, "count": v, "percent": round(v / total * 100, 1)}
            for k, v in d.items()
        ]
        items.sort(key=lambda x: x["count"], reverse=True)
        return items

    current_count = len(current)
    trend_pct = None
    if days is not None and previous_count > 0:
        trend_pct = round((current_count - previous_count) / previous_count * 100, 1)

    # Sort events by distance and format for the client.
    current.sort(key=lambda x: x[0])
    events = []
    for distance, event in current[:limit]:
        events.append({
            "id": event.id,
            "distance_km": round(distance, 2),
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "state": event.state,
            "city": event.city,
            "neighborhood": event.neighborhood,
            "homicide_type": event.homicide_type,
            "method_of_death": event.method_of_death,
            "victim_count": event.victim_count,
            "victims_summary": event.victims_summary,
            "security_force_involved": event.security_force_involved,
            "title": event.title,
            "latitude": float(event.latitude),
            "longitude": float(event.longitude),
            "location_precision": event.location_precision,
            "source_count": event.source_count,
        })

    return {
        "center": {"lat": lat, "lng": lng},
        "radius_km": radius_km,
        "days": days,
        "summary": {
            "total": current_count,
            "total_victims": total_victims,
            "previous_period_total": previous_count if days is not None else None,
            "trend_pct": trend_pct,
            "security_force_involved": security_involved,
            "by_type": to_sorted(by_type),
            "by_method": to_sorted(by_method),
        },
        "events": events,
    }


@router.get("/map-points")
async def get_map_points(
    session: AsyncSession = Depends(get_session),
    days: int = Query(365, ge=1, le=3650, description="Only events in the last N days"),
    type: str | None = Query(None, description="Filter by homicide type"),
    min_lng: float | None = Query(None, description="Bounding box west longitude"),
    min_lat: float | None = Query(None, description="Bounding box south latitude"),
    max_lng: float | None = Query(None, description="Bounding box east longitude"),
    max_lat: float | None = Query(None, description="Bounding box north latitude"),
    limit: int = Query(100000, ge=1, le=200000),
):
    """
    Return every geocoded event as a compact array for client-side map
    aggregation (deck.gl). Short keys keep the payload small.

    Keys: id, lat, lng, t=homicide_type, m=method_of_death, d=event_date (ISO),
    v=victim_count, s=security_force_involved, c=city, n=neighborhood, st=state,
    p=time_of_day.

    Defaults to the last 365 days. No sort — order is undefined (cheaper for map tiles).
    """
    cutoff, now = _map_window(days)
    query = select(
        UniqueEvent.id,
        UniqueEvent.latitude,
        UniqueEvent.longitude,
        UniqueEvent.homicide_type,
        UniqueEvent.method_of_death,
        UniqueEvent.event_date,
        UniqueEvent.victim_count,
        UniqueEvent.security_force_involved,
        UniqueEvent.city,
        UniqueEvent.neighborhood,
        UniqueEvent.state,
        UniqueEvent.time_of_day,
    ).where(
        UniqueEvent.latitude.isnot(None),
        UniqueEvent.longitude.isnot(None),
        UniqueEvent.event_date >= cutoff,
        UniqueEvent.event_date <= now,
    )

    if type:
        query = query.where(UniqueEvent.homicide_type == type)

    if min_lng is not None and max_lng is not None:
        query = query.where(
            UniqueEvent.longitude >= min_lng,
            UniqueEvent.longitude <= max_lng,
        )
    if min_lat is not None and max_lat is not None:
        query = query.where(
            UniqueEvent.latitude >= min_lat,
            UniqueEvent.latitude <= max_lat,
        )

    query = query.limit(limit)

    result = await session.execute(query)
    rows = result.all()

    points = []
    for r in rows:
        try:
            lat = float(r.latitude)
            lng = float(r.longitude)
        except (TypeError, ValueError):
            continue
        points.append({
            "id": r.id,
            "lat": lat,
            "lng": lng,
            "t": r.homicide_type,
            "m": r.method_of_death,
            "d": r.event_date.isoformat() if r.event_date else None,
            "v": r.victim_count,
            "s": r.security_force_involved,
            "c": r.city,
            "n": r.neighborhood,
            "st": r.state,
            "p": r.time_of_day,
        })

    return {"count": len(points), "points": points}


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
    format: str = Query("csv", pattern="^(csv|json)$"),
    state: str | None = None,
    type: str | None = None,
    types: list[str] | None = Query(None),
    methods: list[str] | None = Query(None),
    periods: list[str] | None = Query(None),
    days: int = Query(365, ge=1, le=3650),
    columns: list[str] | None = Query(None),
):
    """Export geocoded events as CSV, optionally filtered (matches map data window)."""
    cutoff, now = _map_window(days)
    query = select(UniqueEvent).where(
        UniqueEvent.event_date >= cutoff,
        UniqueEvent.event_date <= now,
        UniqueEvent.event_date.isnot(None),
        UniqueEvent.latitude.isnot(None),
        UniqueEvent.longitude.isnot(None),
    )

    if state:
        query = query.where(UniqueEvent.state == state)

    type_filters = list(types or [])
    if type:
        type_filters.append(type)
    if type_filters:
        query = query.where(UniqueEvent.homicide_type.in_(type_filters))

    if methods:
        query = query.where(UniqueEvent.method_of_death.in_(methods))

    if periods:
        query = query.where(UniqueEvent.time_of_day.in_(_expand_period_filters(periods)))

    query = query.order_by(UniqueEvent.event_date.desc().nullslast())

    result = await session.execute(query)
    events = result.scalars().all()

    allowed_columns = set(EXPORT_FIELD_NAMES)
    selected_columns: list[str] | None = None
    if columns:
        selected_columns = [column for column in columns if column in allowed_columns]
        if not selected_columns:
            raise HTTPException(status_code=400, detail="Nenhuma coluna válida selecionada")

    data = []
    for event in events:
        merged_data_str = None
        if event.merged_data:
            merged_data_str = json.dumps(event.merged_data, ensure_ascii=False)

        row = {
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
        }
        if selected_columns:
            row = {key: row[key] for key in selected_columns}
        data.append(row)

    fieldnames = selected_columns or (list(data[0].keys()) if data else EXPORT_FIELD_NAMES)

    if format == "json":
        return Response(
            content=json.dumps(data, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=eventos.json"},
        )

    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eventos.csv"},
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

