"""Public API router for public-facing website."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import math
import csv
import json  # For serializing merged_data
import io

from app.database import get_session
from app.models.unique_event import UniqueEvent
from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews
from app.services.public_filters import (
    apply_public_incident_filter,
    homicide_type_filter,
    homicide_types_filter,
)

router = APIRouter(prefix="/public", tags=["public"])

# Rolling window shared by the map, export, and temporal-scope note.
PUBLIC_MAP_DAYS = 365

# Public data-dictionary fields only (matches UI export groups minus internal pipeline fields).
PUBLIC_EXPORT_FIELD_NAMES = [
    "id",
    "event_family",
    "event_subtype",
    "homicide_type",
    "method_of_death",
    "event_date",
    "time_of_day",
    "country",
    "state",
    "city",
    "neighborhood",
    "street",
    "latitude",
    "longitude",
    "location_precision",
    "victim_count",
    "perpetrator_count",
    "security_force_involved",
    "title",
    "chronological_description",
    "source_count",
    "created_at",
    "updated_at",
]

EXPORT_MAX_ROWS = 50_000


def _map_window(days: int = PUBLIC_MAP_DAYS) -> tuple[datetime, datetime]:
    """Return (cutoff, now) for the public map data window."""
    now = datetime.utcnow()
    return now - timedelta(days=days), now


def _parse_export_date(value: str, field_label: str) -> datetime:
    """Parse YYYY-MM-DD export filter dates."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} inválida. Use o formato AAAA-MM-DD.",
        ) from exc


def _export_date_window(
    *,
    days: int,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime | None, datetime]:
    """Resolve export date bounds from rolling days or explicit range."""
    if not start_date and not end_date:
        cutoff, now = _map_window(days)
        return cutoff, now

    start = _parse_export_date(start_date, "Data inicial") if start_date else None
    end = _parse_export_date(end_date, "Data final") if end_date else datetime.utcnow()
    if end_date:
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    if start and end and start > end:
        raise HTTPException(
            status_code=400,
            detail="A data inicial não pode ser posterior à data final.",
        )

    return start, end


def _expand_period_filters(periods: list[str]) -> list[str]:
    """Match period filters across spelling variants (e.g. manhã / manha)."""
    expanded: set[str] = set()
    for period in periods:
        if period.lower() in ("manhã", "manha"):
            expanded.update(["manhã", "manha"])
        else:
            expanded.add(period)
    return list(expanded)


def _event_to_export_row(event: UniqueEvent, fieldnames: list[str]) -> dict[str, object | None]:
    """Build a single export row restricted to the requested public columns."""
    full_row = {
        "id": event.id,
        "event_family": event.event_family,
        "event_subtype": event.event_subtype,
        "homicide_type": event.homicide_type,
        "method_of_death": event.method_of_death,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "time_of_day": event.time_of_day,
        "country": event.country,
        "state": event.state,
        "city": event.city,
        "neighborhood": event.neighborhood,
        "street": event.street,
        "latitude": float(event.latitude) if event.latitude else None,
        "longitude": float(event.longitude) if event.longitude else None,
        "location_precision": event.location_precision,
        "victim_count": event.victim_count,
        "perpetrator_count": event.perpetrator_count,
        "security_force_involved": event.security_force_involved,
        "title": event.title,
        "chronological_description": event.chronological_description,
        "source_count": event.source_count,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }
    return {key: full_row[key] for key in fieldnames}


def _build_export_query(
    *,
    cutoff: datetime | None,
    end: datetime,
    state: str | None,
    states: list[str] | None,
    cities: list[str] | None,
    type: str | None,
    types: list[str] | None,
    methods: list[str] | None,
    periods: list[str] | None,
):
    """Build the filtered export query (unordered; caller adds order/limit)."""
    query = select(UniqueEvent).where(
        UniqueEvent.event_date.isnot(None),
        UniqueEvent.latitude.isnot(None),
        UniqueEvent.longitude.isnot(None),
    )
    if cutoff is not None:
        query = query.where(UniqueEvent.event_date >= cutoff)
    query = query.where(UniqueEvent.event_date <= end)

    state_filters = list(states or [])
    if state:
        state_filters.append(state)
    if state_filters:
        query = query.where(UniqueEvent.state.in_(state_filters))

    if cities:
        query = query.where(UniqueEvent.city.in_(cities))

    type_filters = list(types or [])
    if type:
        type_filters.append(type)
    if type_filters:
        query = query.where(homicide_types_filter(type_filters))

    if methods:
        query = query.where(UniqueEvent.method_of_death.in_(methods))

    if periods:
        query = query.where(UniqueEvent.time_of_day.in_(_expand_period_filters(periods)))

    query = apply_public_incident_filter(query)
    return query.order_by(UniqueEvent.event_date.desc().nullslast())


def _resolve_export_columns(columns: list[str] | None) -> list[str]:
    """Validate and resolve requested export columns against the public allowlist."""
    allowed_columns = set(PUBLIC_EXPORT_FIELD_NAMES)
    if not columns:
        return list(PUBLIC_EXPORT_FIELD_NAMES)

    selected_columns = [column for column in columns if column in allowed_columns]
    if not selected_columns:
        raise HTTPException(status_code=400, detail="Nenhuma coluna válida selecionada")
    return selected_columns


def _stream_export_csv(
    session: AsyncSession,
    query,
    fieldnames: list[str],
):
    """Return an async CSV byte generator for the export query."""
    async def generate():
        header_buffer = io.StringIO()
        writer = csv.DictWriter(header_buffer, fieldnames=fieldnames)
        writer.writeheader()
        yield header_buffer.getvalue()

        limited_query = query.limit(EXPORT_MAX_ROWS)
        stream = await session.stream_scalars(limited_query)
        async for event in stream:
            row_buffer = io.StringIO()
            row_writer = csv.DictWriter(row_buffer, fieldnames=fieldnames)
            row_writer.writerow(_event_to_export_row(event, fieldnames))
            yield row_buffer.getvalue()

    return generate()


async def _load_export_rows(
    session: AsyncSession,
    query,
    fieldnames: list[str],
) -> tuple[list[dict[str, object | None]], bool]:
    """Load export rows for JSON responses, respecting the row cap."""
    limited_query = query.limit(EXPORT_MAX_ROWS + 1)
    result = await session.execute(limited_query)
    events = result.scalars().all()
    truncated = len(events) > EXPORT_MAX_ROWS
    if truncated:
        events = events[:EXPORT_MAX_ROWS]
    rows = [_event_to_export_row(event, fieldnames) for event in events]
    return rows, truncated


@router.get("/stats")
async def get_public_stats(session: AsyncSession = Depends(get_session)):
    """Get public overview stats."""
    
    # Total events
    total = await session.scalar(
        apply_public_incident_filter(select(func.count(UniqueEvent.id)))
    )
    
    # Current datetime for rolling window calculations
    now = datetime.utcnow()
    
    # Last 7 days - events from 7 days ago to now (exclude future events)
    last_7_days_start = now - timedelta(days=7)
    last_7_days = await session.scalar(
        apply_public_incident_filter(
            select(func.count(UniqueEvent.id)).where(
                UniqueEvent.event_date >= last_7_days_start,
                UniqueEvent.event_date <= now,
                UniqueEvent.event_date.isnot(None),
            )
        )
    )
    
    # Last 30 days - events from 30 days ago to now (exclude future events)
    last_30_days_start = now - timedelta(days=30)
    last_30_days = await session.scalar(
        apply_public_incident_filter(
            select(func.count(UniqueEvent.id)).where(
                UniqueEvent.event_date >= last_30_days_start,
                UniqueEvent.event_date <= now,
                UniqueEvent.event_date.isnot(None),
            )
        )
    )
    
    # Earliest event in the public map window (geocoded, last 365 days).
    cutoff, now = _map_window(PUBLIC_MAP_DAYS)
    earliest = await session.scalar(
        apply_public_incident_filter(
            select(func.min(UniqueEvent.event_date)).where(
                UniqueEvent.event_date >= cutoff,
                UniqueEvent.event_date <= now,
                UniqueEvent.event_date.isnot(None),
                UniqueEvent.latitude.isnot(None),
                UniqueEvent.longitude.isnot(None),
            )
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

    query = apply_public_incident_filter(
        select(
            func.date(UniqueEvent.event_date).label("date"),
            func.count(UniqueEvent.id).label("count"),
        ).where(
            UniqueEvent.event_date >= cutoff,
            UniqueEvent.event_date.isnot(None),
        )
    ).group_by(func.date(UniqueEvent.event_date)).order_by(
        func.date(UniqueEvent.event_date).asc()
    )

    result = await session.execute(query)
    rows = result.all()
    
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

    query = apply_public_incident_filter(
        select(UniqueEvent).where(
            UniqueEvent.latitude.isnot(None),
            UniqueEvent.longitude.isnot(None),
            UniqueEvent.latitude >= min_lat,
            UniqueEvent.latitude <= max_lat,
            UniqueEvent.longitude >= min_lng,
            UniqueEvent.longitude <= max_lng,
        )
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

    Keys: id, lat, lng, f=event_family, su=event_subtype, t=homicide_type (legacy),
    m=method_of_death, d=event_date (ISO), v=victim_count, s=security_force_involved,
    c=city, n=neighborhood, st=state, p=time_of_day.

    Defaults to the last 365 days. No sort — order is undefined (cheaper for map tiles).
    """
    cutoff, now = _map_window(days)
    query = apply_public_incident_filter(
        select(
            UniqueEvent.id,
            UniqueEvent.latitude,
            UniqueEvent.longitude,
            UniqueEvent.event_family,
            UniqueEvent.event_subtype,
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
    )

    if type:
        query = query.where(homicide_type_filter(type))

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
            "f": r.event_family,
            "su": r.event_subtype,
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
    query = apply_public_incident_filter(select(UniqueEvent))
    count_query = apply_public_incident_filter(select(func.count(UniqueEvent.id)))
    
    # Apply filters
    if state:
        query = query.where(UniqueEvent.state == state)
        count_query = count_query.where(UniqueEvent.state == state)
    
    if type:
        query = query.where(homicide_type_filter(type))
        count_query = count_query.where(homicide_type_filter(type))
    
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
            "event_family": event.event_family,
            "event_subtype": event.event_subtype,
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
    request: Request,
    session: AsyncSession = Depends(get_session),
    format: str = Query("csv", pattern="^(csv|json)$"),
    state: str | None = None,
    states: list[str] | None = Query(None),
    cities: list[str] | None = Query(None),
    type: str | None = None,
    types: list[str] | None = Query(None),
    methods: list[str] | None = Query(None),
    periods: list[str] | None = Query(None),
    days: int = Query(365, ge=1, le=3650),
    columns: list[str] | None = Query(None),
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD, inclusive)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD, inclusive)"),
):
    """Export geocoded events as CSV, optionally filtered (matches map data window)."""
    from app.services.geocode_protection import enforce_export_rate_limit, get_client_ip

    client_ip = get_client_ip(request)
    await enforce_export_rate_limit(client_ip)

    cutoff, end = _export_date_window(days=days, start_date=start_date, end_date=end_date)
    query = _build_export_query(
        cutoff=cutoff,
        end=end,
        state=state,
        states=states,
        cities=cities,
        type=type,
        types=types,
        methods=methods,
        periods=periods,
    )
    fieldnames = _resolve_export_columns(columns)

    if format == "json":
        rows, truncated = await _load_export_rows(session, query, fieldnames)
        headers = {"Content-Disposition": "attachment; filename=eventos.json"}
        if truncated:
            headers["X-Export-Truncated"] = "true"
        return Response(
            content=json.dumps(rows, ensure_ascii=False),
            media_type="application/json",
            headers=headers,
        )

    generator = _stream_export_csv(session, query, fieldnames)
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eventos.csv"},
    )


def _format_source_article(source: SourceGoogleNews) -> dict:
    """Format a linked Google News source for the public detail response."""
    return {
        "id": source.id,
        "headline": source.headline,
        "publisher_name": source.publisher_name,
        "url": source.resolved_url,
        "google_news_url": source.google_news_url,
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "kind": "source",
    }


def _format_raw_fallback_article(raw_event: RawEvent, fallback_title: str | None) -> dict:
    """Fallback article when a raw event has no linked SourceGoogleNews row."""
    headline = raw_event.title or fallback_title
    return {
        "id": -raw_event.id if raw_event.id is not None else 0,
        "headline": headline,
        "publisher_name": None,
        "url": None,
        "google_news_url": None,
        "published_at": raw_event.event_date.isoformat() if raw_event.event_date else None,
        "kind": "raw_fallback",
    }


async def _build_public_event_sources(
    raw_events: list[RawEvent],
    session: AsyncSession,
    *,
    fallback_title: str | None,
) -> list[dict]:
    """Build deduplicated, sorted source articles from linked raw events."""
    source_ids = list({re.source_google_news_id for re in raw_events if re.source_google_news_id})
    sources_by_id: dict[int, SourceGoogleNews] = {}
    if source_ids:
        sources_result = await session.execute(
            select(SourceGoogleNews).where(SourceGoogleNews.id.in_(source_ids))
        )
        for source in sources_result.scalars().all():
            sources_by_id[source.id] = source

    seen_source_ids: set[int] = set()
    articles: list[dict] = []
    for raw_event in raw_events:
        source_id = raw_event.source_google_news_id
        if source_id and source_id in sources_by_id and source_id not in seen_source_ids:
            seen_source_ids.add(source_id)
            articles.append(_format_source_article(sources_by_id[source_id]))
        elif not source_id:
            articles.append(_format_raw_fallback_article(raw_event, fallback_title))

    def sort_key(article: dict) -> tuple[int, str]:
        published = article.get("published_at")
        return (0 if published else 1, published or "")

    articles.sort(key=sort_key, reverse=True)
    return articles


def _format_public_event_detail(event: UniqueEvent, sources: list[dict]) -> dict:
    """Serialize a unique event for the public detail endpoint."""
    return {
        "id": event.id,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "time_of_day": event.time_of_day,
        "country": event.country,
        "state": event.state,
        "city": event.city,
        "neighborhood": event.neighborhood,
        "street": event.street,
        "event_family": event.event_family,
        "event_subtype": event.event_subtype,
        "homicide_type": event.homicide_type,
        "method_of_death": event.method_of_death,
        "victim_count": event.victim_count,
        "victims_summary": event.victims_summary,
        "perpetrator_count": event.perpetrator_count,
        "security_force_involved": event.security_force_involved,
        "title": event.title,
        "chronological_description": event.chronological_description,
        "latitude": float(event.latitude) if event.latitude else None,
        "longitude": float(event.longitude) if event.longitude else None,
        "location_precision": event.location_precision,
        "formatted_address": event.formatted_address,
        "source_count": event.source_count,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
        "sources": sources,
    }


@router.get("/events/{event_id}")
async def get_public_event_by_id(
    event_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single public event by ID with all related sources."""
    
    # Fetch the unique event (exclude rows filtered from public views)
    result = await session.execute(
        apply_public_incident_filter(
            select(UniqueEvent).where(UniqueEvent.id == event_id)
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    raw_events_result = await session.execute(
        select(RawEvent).where(RawEvent.unique_event_id == event_id)
    )
    raw_events = raw_events_result.scalars().all()
    sources = await _build_public_event_sources(
        raw_events,
        session,
        fallback_title=event.title,
    )

    return _format_public_event_detail(event, sources)

