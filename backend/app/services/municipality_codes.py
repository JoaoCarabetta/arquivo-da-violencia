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

Production loads full municipality polygons from geobr (cached on disk).
Tests use a small fixture (Rio, Brasília, São Paulo) - no live API calls in tests.

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


# Global cache for municipality polygons
_MUNICIPALITY_POLYGONS_CACHE = None
_USE_TEST_FIXTURE = False  # Set to True in tests


def set_test_mode(use_fixture: bool = True):
    """
    Enable or disable test fixture mode.
    
    When True, uses the small 3-municipality fixture for tests.
    When False (production), loads full geobr municipality polygons.
    
    Tests should call this before using lookup functions.
    """
    global _USE_TEST_FIXTURE, _MUNICIPALITY_POLYGONS_CACHE
    _USE_TEST_FIXTURE = use_fixture
    _MUNICIPALITY_POLYGONS_CACHE = None  # Clear cache when mode changes


def _get_polygon_cache_path() -> Path:
    """Get the path to the cached municipality polygons file."""
    # Store in app data directory
    cache_dir = Path(__file__).parent.parent / "data"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "municipality_polygons_cache.json"


def _load_test_fixture() -> dict:
    """Load the small test fixture (Rio, Brasília, São Paulo)."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "municipality_polygons.json"
    
    if not fixture_path.exists():
        logger.warning(f"[MunicipalityLookup] Test fixture not found at {fixture_path}")
        return {"features": []}
    
    try:
        with open(fixture_path, "r") as f:
            data = json.load(f)
        logger.info(f"[MunicipalityLookup] Loaded {len(data.get('features', []))} municipalities from test fixture")
        return data
    except Exception as e:
        logger.error(f"[MunicipalityLookup] Failed to load test fixture: {e}")
        return {"features": []}


def _load_geobr_polygons() -> dict:
    """
    Load full municipality polygons from geobr (production).
    
    First checks for cached file on disk. If not found or stale,
    downloads from geobr and caches it.
    
    Returns GeoJSON FeatureCollection with all ~5,570 Brazilian municipalities.
    """
    cache_path = _get_polygon_cache_path()
    
    # Try to load from cache first
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            logger.info(f"[MunicipalityLookup] Loaded {len(data.get('features', []))} municipalities from cache")
            return data
        except Exception as e:
            logger.warning(f"[MunicipalityLookup] Failed to load cache, will download: {e}")
    
    # Download from geobr
    logger.info("[MunicipalityLookup] Downloading municipality polygons from geobr...")
    try:
        from geobr import read_municipality
        import geopandas as gpd
        
        # Load all municipalities (year 2022 to match population data)
        gdf = read_municipality(year=2022, verbose=False)
        
        # Convert to GeoJSON format
        geojson_str = gdf.to_json()
        data = json.loads(geojson_str)
        
        # Cache to disk
        with open(cache_path, "w") as f:
            json.dump(data, f)
        
        logger.info(f"[MunicipalityLookup] Downloaded and cached {len(data.get('features', []))} municipalities")
        return data
        
    except ImportError as e:
        logger.error(f"[MunicipalityLookup] Missing geobr package: {e}. Install with: pip install geobr")
        return {"features": []}
    except Exception as e:
        logger.error(f"[MunicipalityLookup] Failed to download geobr polygons: {e}")
        return {"features": []}


def _load_municipality_polygons() -> dict:
    """
    Load municipality polygon data.
    
    In test mode: uses small fixture (Rio, Brasília, São Paulo).
    In production mode: loads full geobr polygons (~5,570 municipalities).
    
    Results are cached in memory after first load.
    """
    global _MUNICIPALITY_POLYGONS_CACHE
    
    if _MUNICIPALITY_POLYGONS_CACHE is not None:
        return _MUNICIPALITY_POLYGONS_CACHE
    
    if _USE_TEST_FIXTURE:
        _MUNICIPALITY_POLYGONS_CACHE = _load_test_fixture()
    else:
        _MUNICIPALITY_POLYGONS_CACHE = _load_geobr_polygons()
    
    return _MUNICIPALITY_POLYGONS_CACHE


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
    
    Production uses full geobr municipality polygons (~5,570 municipalities).
    Tests use a small fixture (Rio, Brasília, São Paulo) - no live API calls.
    
    Args:
        session: Database session (not used in current implementation, kept for API consistency)
        latitude: Latitude
        longitude: Longitude
    
    Returns:
        7-digit IBGE municipality code, or None if not found
    """
    polygons = _load_municipality_polygons()
    
    for feature in polygons.get("features", []):
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})
        
        # Extract municipality code - geobr uses 'code_muni', fixture also uses 'code_muni'
        code_muni = properties.get("code_muni")
        if not code_muni:
            continue
        
        # Handle both Polygon and MultiPolygon geometries
        geom_type = geometry.get("type")
        
        if geom_type == "Polygon":
            coords_list = geometry.get("coordinates", [])
            for coords in coords_list:
                if point_in_polygon(latitude, longitude, coords):
                    logger.debug(
                        f"[MunicipalityLookup] Point ({latitude}, {longitude}) -> "
                        f"{properties.get('name_muni', 'Unknown')} ({code_muni})"
                    )
                    return int(code_muni)
        
        elif geom_type == "MultiPolygon":
            # MultiPolygon is a list of Polygons
            for polygon in geometry.get("coordinates", []):
                for coords in polygon:
                    if point_in_polygon(latitude, longitude, coords):
                        logger.debug(
                            f"[MunicipalityLookup] Point ({latitude}, {longitude}) -> "
                            f"{properties.get('name_muni', 'Unknown')} ({code_muni})"
                        )
                        return int(code_muni)
    
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
