"""
Geocoding Service - Google Maps Geocoding API Integration

Geocodes incidents using Google Maps Geocoding API and determines
coordinate precision based on API response.
"""
import os
import time
from flask import current_app
import googlemaps
from loguru import logger
from app.models import Incident


# Google Maps API client (initialized on first use)
_gmaps_client = None


def get_gmaps_client():
    """Get or initialize Google Maps API client."""
    global _gmaps_client
    
    if _gmaps_client is None:
        api_key = current_app.config.get('GOOGLE_MAPS_API_KEY')
        if not api_key:
            logger.warning("⚠️ GOOGLE_MAPS_API_KEY not configured, geocoding will be skipped")
            return None
        
        try:
            _gmaps_client = googlemaps.Client(key=api_key)
            logger.info("✅ Google Maps client initialized")
        except Exception as e:
            logger.error(f"⚠️ Error initializing Google Maps client: {e}")
            return None
    
    return _gmaps_client


def build_geocoding_query(incident):
    """
    Build a geocoding query string from incident location fields.
    
    Args:
        incident: Incident object with location fields
        
    Returns:
        str: Geocoding query string, or None if insufficient location data
    """
    parts = []
    
    # Build query from most specific to least specific
    if incident.street:
        parts.append(incident.street)
    
    if incident.neighborhood:
        parts.append(incident.neighborhood)
    
    if incident.city:
        parts.append(incident.city)
    elif not parts:  # If no city but we have other parts, default to Rio
        parts.append("Rio de Janeiro")
    
    if incident.state:
        parts.append(incident.state)
    elif not parts:  # If no state but we have other parts, default to RJ
        parts.append("Rio de Janeiro")
    
    if incident.country:
        parts.append(incident.country)
    elif not parts:  # If no country but we have other parts, default to Brasil
        parts.append("Brasil")
    
    if not parts:
        return None
    
    query = ", ".join(parts)
    return query


def determine_precision(geocode_result):
    """
    Determine location precision from Google Maps Geocoding API response.
    
    Args:
        geocode_result: Single result from geocoding API response
        
    Returns:
        str: Precision level ('exact', 'approximate', 'neighborhood_center', 'city_center')
    """
    location_type = geocode_result.get('geometry', {}).get('location_type', '')
    address_components = geocode_result.get('address_components', [])
    types = geocode_result.get('types', [])
    
    # Check location_type from geometry
    if location_type == 'ROOFTOP':
        # Exact address coordinates
        return 'exact'
    elif location_type == 'RANGE_INTERPOLATED':
        # Approximate location on a street
        return 'approximate'
    elif location_type == 'GEOMETRIC_CENTER':
        # Center of a polygon (neighborhood, city, etc.)
        # Check address components to determine level
        has_neighborhood = any('sublocality' in comp.get('types', []) or 
                              'neighborhood' in comp.get('types', []) 
                              for comp in address_components)
        has_city = any('locality' in comp.get('types', []) or 
                      'administrative_area_level_2' in comp.get('types', [])
                      for comp in address_components)
        
        if has_neighborhood:
            return 'neighborhood_center'
        elif has_city:
            return 'city_center'
        else:
            return 'approximate'
    elif location_type == 'APPROXIMATE':
        # Approximate location
        # Check if it's a neighborhood or city center
        has_neighborhood = any('sublocality' in comp.get('types', []) or 
                              'neighborhood' in comp.get('types', []) 
                              for comp in address_components)
        has_city = any('locality' in comp.get('types', []) or 
                      'administrative_area_level_2' in comp.get('types', [])
                      for comp in address_components)
        
        if has_neighborhood:
            return 'neighborhood_center'
        elif has_city:
            return 'city_center'
        else:
            return 'approximate'
    else:
        # Fallback: check types
        if 'street_address' in types or 'premise' in types:
            return 'exact'
        elif 'route' in types or 'street_number' in types:
            return 'approximate'
        elif 'sublocality' in types or 'neighborhood' in types:
            return 'neighborhood_center'
        elif 'locality' in types or 'administrative_area_level_2' in types:
            return 'city_center'
        else:
            return 'approximate'


def geocode_incident(incident, retry_count=3, retry_delay=1):
    """
    Geocode an incident using Google Maps Geocoding API.
    
    Args:
        incident: Incident object to geocode
        retry_count: Number of retry attempts on failure
        retry_delay: Delay between retries in seconds
        
    Returns:
        tuple: (latitude, longitude, precision) or (None, None, None) on failure
    """
    client = get_gmaps_client()
    if not client:
        return None, None, None
    
    # Skip if already geocoded (unless we want to re-geocode)
    if incident.latitude is not None and incident.longitude is not None:
        logger.debug(f"    [Geocoding] Incident {incident.id} already geocoded, skipping")
        return incident.latitude, incident.longitude, incident.location_precision
    
    # Build query
    query = build_geocoding_query(incident)
    if not query:
        logger.debug(f"    [Geocoding] Incident {incident.id}: insufficient location data, skipping")
        return None, None, None
    
    logger.debug(f"    [Geocoding] Geocoding Incident {incident.id}: {query}")
    
    # Retry logic
    for attempt in range(retry_count):
        try:
            # Call Google Maps Geocoding API
            results = client.geocode(query)
            
            if not results:
                logger.warning(f"    [Geocoding] No results found for: {query}")
                return None, None, None
            
            # Use first result (most relevant)
            result = results[0]
            
            # Extract coordinates
            location = result.get('geometry', {}).get('location', {})
            latitude = location.get('lat')
            longitude = location.get('lng')
            
            if latitude is None or longitude is None:
                logger.warning(f"    [Geocoding] Invalid coordinates in API response")
                return None, None, None
            
            # Determine precision
            precision = determine_precision(result)
            
            logger.info(f"    [Geocoding] ✅ Geocoded: ({latitude}, {longitude}), precision: {precision}")
            return latitude, longitude, precision
            
        except googlemaps.exceptions.HTTPError as e:
            if e.status_code == 429:  # Rate limit exceeded
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"    [Geocoding] Rate limit exceeded, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"    [Geocoding] HTTP error: {e}")
                return None, None, None
                
        except Exception as e:
            logger.exception(f"    [Geocoding] Error geocoding incident {incident.id}: {e}")
            if attempt < retry_count - 1:
                time.sleep(retry_delay)
                continue
            return None, None, None
    
    return None, None, None


def geocode_incident_and_save(incident, commit=True):
    """
    Geocode an incident and save coordinates to database.
    
    Args:
        incident: Incident object to geocode
        commit: Whether to commit the database session
        
    Returns:
        bool: True if geocoding succeeded, False otherwise
    """
    from app.extensions import db
    
    latitude, longitude, precision = geocode_incident(incident)
    
    if latitude is not None and longitude is not None:
        incident.latitude = latitude
        incident.longitude = longitude
        incident.location_precision = precision
        
        if commit:
            db.session.commit()
        
        return True
    
    return False

