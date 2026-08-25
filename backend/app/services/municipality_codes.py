"""
Municipality code backfill service for existing UniqueEvents (issue #174, #179).

This module provides functions to backfill IBGE municipality codes for existing
UniqueEvents that were geocoded before the municipality_code field existed.

Issue #179 improvements:
- Point-in-polygon lookup using geobr municipality geometries (PRIMARY when coordinates exist)
- Improved name-based lookup with case/accent folding (FALLBACK when no coordinates)
- Full state name support
- Unique city without state support
- DF administrative regions map to Brasília

Only Brazilian municipalities get codes. Ambiguous city names (no state) are
skipped unless unique - we do not guess.
"""

import json
import os
from typing import Dict, Optional
from pathlib import Path
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text
from loguru import logger

from app.services.ibge_population import lookup_city_codes


# Cache for municipality polygons (loaded once from fixture)
_MUNICIPALITY_POLYGONS = None


def _load_municipality_polygons():
    """
    Load municipality polygon fixtures from JSON.
    
    In production, this would load from geobr. For tests and offline use,
    we use a fixture with a subset of municipalities (Rio, Brasília, São Paulo).
    """
    global _MUNICIPALITY_POLYGONS
    
    if _MUNICIPALITY_POLYGONS is not None:
        return _MUNICIPALITY_POLYGONS
    
    fixture_path = Path(__file__).parent.parent / "fixtures" / "municipality_polygons.json"
    
    if not fixture_path.exists():
        logger.warning(f"[MunicipalityLookup] Polygon fixture not found at {fixture_path}")
        _MUNICIPALITY_POLYGONS = {"features": []}
        return _MUNICIPALITY_POLYGONS
    
    try:
        with open(fixture_path, "r") as f:
            _MUNICIPALITY_POLYGONS = json.load(f)
        logger.info(f"[MunicipalityLookup] Loaded {len(_MUNICIPALITY_POLYGONS.get('features', []))} municipality polygons")
    except Exception as e:
        logger.error(f"[MunicipalityLookup] Failed to load polygon fixture: {e}")
        _MUNICIPALITY_POLYGONS = {"features": []}
    
    return _MUNICIPALITY_POLYGONS


def point_in_polygon(lat: float, lng: float, polygon_coords: list) -> bool:
    """
    Check if a point (lat, lng) is inside a polygon using ray casting algorithm.
    
    Args:
        lat: Latitude
        lng: Longitude
        polygon_coords: List of [lng, lat] coordinate pairs forming the polygon
    
    Returns:
        True if point is inside polygon, False otherwise
    """
    inside = False
    n = len(polygon_coords)
    
    p1_lng, p1_lat = polygon_coords[0]
    
    for i in range(1, n + 1):
        p2_lng, p2_lat = polygon_coords[i % n]
        
        if lat > min(p1_lat, p2_lat):
            if lat <= max(p1_lat, p2_lat):
                if lng <= max(p1_lng, p2_lng):
                    if p1_lat != p2_lat:
                        x_intersection = (lat - p1_lat) * (p2_lng - p1_lng) / (p2_lat - p1_lat) + p1_lng
                    if p1_lng == p2_lng or lng <= x_intersection:
                        inside = not inside
        
        p1_lng, p1_lat = p2_lng, p2_lat
    
    return inside


async def lookup_municipality_code_from_coordinates(
    session: AsyncSession,
    latitude: float,
    longitude: float
) -> Optional[int]:
    """
    Lookup IBGE municipality code from lat/lng using point-in-polygon.
    
    This is the PRIMARY lookup method when coordinates are available (issue #179).
    Falls back to None if the point doesn't match any municipality polygon.
    
    Args:
        session: Database session (not used in fixture mode, but kept for API consistency)
        latitude: Latitude
        longitude: Longitude
    
    Returns:
        7-digit IBGE municipality code, or None if not found
    """
    polygons = _load_municipality_polygons()
    
    for feature in polygons.get("features", []):
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})
        
        if geometry.get("type") == "Polygon":
            coords = geometry.get("coordinates", [[]])[0]
            
            if point_in_polygon(latitude, longitude, coords):
                code_muni = properties.get("code_muni")
                if code_muni:
                    logger.debug(
                        f"[MunicipalityLookup] Point ({latitude}, {longitude}) -> "
                        f"{properties.get('name_muni')} ({code_muni})"
                    )
                    return code_muni
    
    logger.debug(f"[MunicipalityLookup] No polygon match for ({latitude}, {longitude})")
    return None


async def backfill_municipality_codes(
    session: AsyncSession,
    limit: int | None = None
) -> Dict[str, int]:
    """
    Backfill municipality_code for existing UniqueEvents that lack it.
    
    Issue #179: Uses point-in-polygon lookup when coordinates exist (PRIMARY),
    falls back to name-based lookup when no coordinates (SECONDARY).
    
    Priority:
    1. If lat/lng exist: use point-in-polygon on municipality geometries
    2. If no coordinates: use name-based lookup (city+state or unique city name)
    
    Only updates events where:
    - municipality_code IS NULL
    - country is BR, Brasil, or NULL (default BR)
    
    Does NOT guess codes for:
    - Events where point-in-polygon finds no match AND name lookup fails
    - Non-Brazilian events (Chile, etc.)
    
    Args:
        session: Database session
        limit: Maximum number of events to backfill (for batching)
    
    Returns:
        Dictionary with counts: {
            "updated": int,
            "skipped_no_city": int,
            "skipped_no_state": int,
            "skipped_non_brazil": int,
            "skipped_not_found": int,
        }
    """
    # Find events that need codes: Brazilian events without code
    query = text("""
        SELECT id, city, state, country, latitude, longitude
        FROM unique_event
        WHERE municipality_code IS NULL
          AND (country IN ('BR', 'Brasil') OR country IS NULL)
        ORDER BY id
    """)
    
    if limit:
        query = text(str(query) + f" LIMIT {limit}")
    
    result = await session.execute(query)
    events = result.fetchall()
    
    if not events:
        logger.info("[Backfill] No events to backfill")
        return {
            "updated": 0,
            "skipped_no_city": 0,
            "skipped_no_state": 0,
            "skipped_non_brazil": 0,
            "skipped_not_found": 0,
        }
    
    logger.info(f"[Backfill] Found {len(events)} events to process")
    
    updated = 0
    not_found = 0
    
    for event in events:
        event_id = event[0]
        city = event[1]
        state = event[2]
        country = event[3]
        latitude = event[4]
        longitude = event[5]
        
        code = None
        
        # Priority 1: Point-in-polygon if coordinates exist
        if latitude is not None and longitude is not None:
            try:
                lat_float = float(latitude)
                lng_float = float(longitude)
                code = await lookup_municipality_code_from_coordinates(
                    session,
                    lat_float,
                    lng_float
                )
                if code:
                    logger.debug(f"[Backfill] Event {event_id}: polygon lookup -> {code}")
            except (ValueError, TypeError) as e:
                logger.warning(f"[Backfill] Event {event_id}: invalid coordinates: {e}")
        
        # Priority 2: Name-based lookup if no code from coordinates
        if code is None:
            # Build lookup for this single event
            code_map = await lookup_city_codes(
                session,
                cities=[city],
                states=[state]
            )
            code = code_map.get((city, state))
            if code:
                logger.debug(f"[Backfill] Event {event_id}: name lookup -> {code}")
        
        # Update if we found a code
        if code:
            await session.execute(
                text("""
                    UPDATE unique_event
                    SET municipality_code = :code,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": event_id, "code": code}
            )
            updated += 1
        else:
            not_found += 1
    
    await session.commit()
    
    logger.info(f"[Backfill] ✅ Updated {updated} events, {not_found} not found")
    
    # Now count the skipped categories
    # Events with no city
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM unique_event
            WHERE municipality_code IS NULL
              AND (country IN ('BR', 'Brasil') OR country IS NULL)
              AND city IS NULL
        """)
    )
    skipped_no_city = result.scalar()
    
    # Events with no state (now this is OK if city is unique, so count is informational)
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM unique_event
            WHERE municipality_code IS NULL
              AND (country IN ('BR', 'Brasil') OR country IS NULL)
              AND city IS NOT NULL
              AND state IS NULL
        """)
    )
    skipped_no_state = result.scalar()
    
    # Non-Brazilian events
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM unique_event
            WHERE municipality_code IS NULL
              AND country IS NOT NULL
              AND country NOT IN ('BR', 'Brasil')
        """)
    )
    skipped_non_brazil = result.scalar()
    
    return {
        "updated": updated,
        "skipped_no_city": skipped_no_city or 0,
        "skipped_no_state": skipped_no_state or 0,
        "skipped_non_brazil": skipped_non_brazil or 0,
        "skipped_not_found": not_found,
    }
