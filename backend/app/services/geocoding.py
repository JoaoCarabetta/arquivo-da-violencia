"""
Geocoding Service - Google Maps Geocoding API

Populates the geolocation columns on UniqueEvent from the textual location
fields (establishment / street / neighborhood / city / state / country) that
were extracted by the LLM during earlier pipeline stages.

Fields populated: latitude, longitude, plus_code, place_id, formatted_address,
location_precision, geocoding_source, geocoding_confidence.

Design notes:
- location_precision is a discrete enum (see PRECISION_* constants below).
- We clamp the precision to the granularity of the input we actually had, so
  we never claim a more precise result than our input supports.
- plus_code is stored verbatim (Google's full ~14m global_code at the resolved
  point). For imprecise events that point is a centroid; uncertainty is
  conveyed by location_precision + geocoding_confidence, not by the plus_code.
- If GOOGLE_MAPS_API_KEY is unset, this module no-ops gracefully so the
  pipeline stays green without a key.
"""

import asyncio
import re
from decimal import Decimal

import httpx
from loguru import logger
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Discrete location_precision values (Portuguese, matching the documented schema)
PRECISION_EXACT = "exato"
PRECISION_APPROXIMATE = "aproximado"
PRECISION_NEIGHBORHOOD = "centro do bairro"
PRECISION_CITY = "centro da cidade"

GEOCODING_SOURCE = "google_maps"
GEOCODING_SOURCE_NONE = "none"  # sentinel: attempted, no usable result -> don't retry

# Ordering from most precise (0) to least precise (3). Used to "clamp" the
# returned precision so it is never finer than the input we provided.
_PRECISION_RANK = {
    PRECISION_EXACT: 0,
    PRECISION_APPROXIMATE: 1,
    PRECISION_NEIGHBORHOOD: 2,
    PRECISION_CITY: 3,
}

# Confidence heuristic keyed on Google's geometry.location_type.
_CONFIDENCE_BY_LOCATION_TYPE = {
    "ROOFTOP": 0.95,
    "RANGE_INTERPOLATED": 0.75,
    "GEOMETRIC_CENTER": 0.55,
    "APPROXIMATE": 0.4,
}

# --- Open Location Code (Plus Code) encoding --------------------------------
# The Geocoding API frequently omits plus_code from the response. Google's
# `global_code` is just the Open Location Code of the resolved point, so we
# derive it ourselves from lat/lng to keep the field populated. This is the
# official OLC algorithm (validated against Google's reference test vectors).
_OLC_ALPHABET = "23456789CFGHJMPQRVWX"
_OLC_SEPARATOR = "+"
_OLC_SEPARATOR_POSITION = 8
_OLC_PADDING = "0"
_OLC_PAIR_RESOLUTIONS = [20.0, 1.0, 0.05, 0.0025, 0.000125]
_OLC_DEFAULT_LENGTH = 10  # ~14m grid square, matches Google's global_code


def encode_plus_code(latitude, longitude, code_length: int = _OLC_DEFAULT_LENGTH) -> str:
    """Encode a lat/lng to an Open Location Code (Plus Code) global_code."""
    lat = min(90.0, max(-90.0, float(latitude)))
    lng = (float(longitude) + 180.0) % 360.0 - 180.0
    if lat >= 90:  # nudge off the north pole so it stays in the lowest cell
        lat -= 0.000125
    adj_lat = lat + 90.0
    adj_lng = lng + 180.0
    code = ""
    n = 0
    while n < code_length:
        place_value = _OLC_PAIR_RESOLUTIONS[n // 2]
        digit = int(adj_lat / place_value)
        adj_lat -= digit * place_value
        code += _OLC_ALPHABET[digit]
        n += 1
        digit = int(adj_lng / place_value)
        adj_lng -= digit * place_value
        code += _OLC_ALPHABET[digit]
        n += 1
        if n == _OLC_SEPARATOR_POSITION and n < code_length:
            code += _OLC_SEPARATOR
    if len(code) < _OLC_SEPARATOR_POSITION:
        code += _OLC_PADDING * (_OLC_SEPARATOR_POSITION - len(code))
    if len(code) == _OLC_SEPARATOR_POSITION:
        code += _OLC_SEPARATOR
    return code


def _coarser(a: str, b: str) -> str:
    """Return the coarser (less precise) of two precision labels."""
    return a if _PRECISION_RANK[a] >= _PRECISION_RANK[b] else b


def _input_granularity(event) -> str:
    """
    Best precision the input can support, based on the most specific field
    we actually have. Used to clamp Google's returned precision.
    """
    if getattr(event, "establishment", None) or getattr(event, "street", None):
        return PRECISION_APPROXIMATE
    if getattr(event, "neighborhood", None):
        return PRECISION_NEIGHBORHOOD
    return PRECISION_CITY


def build_address_query(event) -> str | None:
    """
    Compose a Google-friendly address query from the structured location fields.
    Returns None if there is not enough information (no city).
    """
    if not getattr(event, "city", None):
        return None

    parts = [
        getattr(event, "establishment", None),
        getattr(event, "street", None),
        getattr(event, "neighborhood", None),
        getattr(event, "city", None),
        getattr(event, "state", None),
        getattr(event, "country", None) or "Brasil",
    ]
    return ", ".join(p for p in parts if p)


def _precision_from_result(result: dict) -> str:
    """
    Map a Google geocoding result to one of the four discrete precision buckets,
    using the result's `types` first (coarse buckets) then `location_type`.
    """
    types = set(result.get("types", []))
    location_type = result.get("geometry", {}).get("location_type", "")

    # Coarse buckets take priority: a locality result is a city centroid even if
    # location_type happens to be GEOMETRIC_CENTER.
    if types & {"locality", "administrative_area_level_2", "administrative_area_level_1", "political"} and not (
        types & {"street_address", "premise", "route", "neighborhood", "sublocality"}
    ):
        return PRECISION_CITY
    if types & {"neighborhood", "sublocality", "sublocality_level_1"}:
        return PRECISION_NEIGHBORHOOD
    if types & {"street_address", "premise", "establishment", "point_of_interest"} or location_type == "ROOFTOP":
        return PRECISION_EXACT
    if types & {"route"} or location_type in ("RANGE_INTERPOLATED", "GEOMETRIC_CENTER"):
        return PRECISION_APPROXIMATE
    # Fallback for APPROXIMATE / unknown
    return PRECISION_CITY


def parse_geocode_result(result: dict, input_granularity: str) -> dict:
    """Extract the geolocation fields from a single Google result dict."""
    geometry = result.get("geometry", {})
    location = geometry.get("location", {})
    location_type = geometry.get("location_type", "")

    precision = _precision_from_result(result)
    # Never claim a more precise result than the input supports.
    precision = _coarser(precision, input_granularity)

    lat = location.get("lat")
    lng = location.get("lng")

    # Prefer Google's plus_code; fall back to deriving it from the point since
    # the Geocoding API often omits it.
    plus_code = (result.get("plus_code") or {}).get("global_code")
    if not plus_code and lat is not None and lng is not None:
        plus_code = encode_plus_code(lat, lng)

    return {
        "latitude": lat,
        "longitude": lng,
        "plus_code": plus_code,
        "place_id": result.get("place_id"),
        "formatted_address": result.get("formatted_address"),
        "location_precision": precision,
        "geocoding_confidence": _CONFIDENCE_BY_LOCATION_TYPE.get(location_type, 0.4),
        "geocoding_source": GEOCODING_SOURCE,
    }


async def geocode_address(
    query: str,
    input_granularity: str = PRECISION_CITY,
    client: httpx.AsyncClient | None = None,
    restrict_country: bool = False,
) -> dict | None:
    """
    Call the Google Maps Geocoding API for a query string.

    Returns a dict of geolocation fields, or None if no usable result / no key.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        logger.warning("[Geocode] GOOGLE_MAPS_API_KEY not set; skipping geocoding")
        return None

    params = {
        "address": query,
        "key": settings.google_maps_api_key,
        "region": "br",
        "language": "pt-BR",
    }
    if restrict_country:
        params["components"] = "country:BR"

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=15.0)
    try:
        response = await client.get(GEOCODE_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"[Geocode] Request failed for '{query}': {e}")
        return None
    finally:
        if owns_client:
            await client.aclose()

    status = data.get("status")
    if status == "ZERO_RESULTS":
        logger.info(f"[Geocode] No results for '{query}'")
        return None
    if status != "OK":
        logger.error(
            f"[Geocode] API status '{status}' for '{query}': {data.get('error_message', '')}"
        )
        return None

    results = data.get("results", [])
    if not results:
        return None

    parsed = parse_geocode_result(results[0], input_granularity)
    if parsed is not None:
        parsed["zoom"] = _zoom_from_google_types(set(results[0].get("types", [])))
    return parsed


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "arquivo-da-violencia/1.0 (+https://arquivodaviolencia.com.br)"


VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"

BRAZIL_COUNTRY_RESULT = {
    "latitude": -14.0,
    "longitude": -52.0,
    "label": "Brasil",
    "source": "preset",
    "zoom": 3.6,
}


def _zoom_from_google_types(types: set[str]) -> float:
    if "country" in types:
        return 3.6
    if types & {"administrative_area_level_1"}:
        return 6.5
    if types & {"locality", "administrative_area_level_2", "administrative_area_level_3"}:
        return 11.0
    if types & {"route", "neighborhood", "sublocality", "street_address", "premise", "postal_code"}:
        return 13.0
    return 11.0


def _zoom_from_nominatim(result: dict) -> float:
    place_type = (result.get("type") or result.get("class") or "").lower()
    if place_type == "country":
        return 3.6
    if place_type in {"state", "region"}:
        return 6.5
    if place_type in {"city", "town", "municipality", "village", "county"}:
        return 11.0
    return 13.0


def normalize_cep(value: str) -> str | None:
    """
    Return a canonical "XXXXX-XXX" CEP if `value` is a Brazilian postal code
    (8 digits, with or without a dash/spaces), otherwise None.
    """
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return None


async def cep_to_address(cep: str, client: httpx.AsyncClient | None = None) -> str | None:
    """
    Resolve a CEP to a human address string via ViaCEP (free, no key).

    Raw CEPs geocode poorly on OpenStreetMap, but the street/neighborhood/city
    that ViaCEP returns geocodes reliably. Returns None if the CEP is unknown.
    """
    digits = re.sub(r"\D", "", cep)
    if len(digits) != 8:
        return None

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        response = await client.get(VIACEP_URL.format(cep=digits))
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"[Geocode] ViaCEP request failed for '{cep}': {e}")
        return None
    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(data, dict) or data.get("erro"):
        return None

    parts = [
        data.get("logradouro"),
        data.get("bairro"),
        data.get("localidade"),
        data.get("uf"),
        "Brasil",
    ]
    address = ", ".join(p for p in parts if p)
    return address or None


async def geocode_user_query(
    query: str,
    client: httpx.AsyncClient | None = None,
) -> dict | None:
    """
    Geocode a free-form user query (CEP, city, neighborhood) into coordinates.

    Used by the public "nearby" search so a visitor can type where they are.
    Prefers Google Maps (when a key is configured) and falls back to the free
    Nominatim/OpenStreetMap service so the feature works without a key.

    Returns {latitude, longitude, label, source} or None.
    """
    query = (query or "").strip()
    if not query:
        return None
    if re.match(r"^(brasil|brazil)$", query, re.I):
        return dict(BRAZIL_COUNTRY_RESULT)
    # Accept CEPs with or without a dash (e.g. "22221150" or "22221-150").
    # Resolve them through ViaCEP first since raw CEPs geocode poorly on OSM.
    cep = normalize_cep(query)
    if cep:
        address = await cep_to_address(cep, client=client)
        query = address or f"{cep}, Brasil"
    elif "brasil" not in query.lower() and "brazil" not in query.lower():
        query = f"{query}, Brasil"

    settings = get_settings()
    if settings.google_maps_api_key:
        fields = await geocode_address(
            query, PRECISION_CITY, client=client, restrict_country=not bool(cep)
        )
        if fields and fields.get("latitude") is not None:
            return {
                "latitude": float(fields["latitude"]),
                "longitude": float(fields["longitude"]),
                "label": fields.get("formatted_address") or query,
                "source": GEOCODING_SOURCE,
                "zoom": fields.get("zoom", 13.0),
            }

    # Free fallback: Nominatim (no API key required).
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "br",
        "accept-language": "pt-BR",
    }
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=15.0)
    try:
        response = await client.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": NOMINATIM_USER_AGENT},
        )
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"[Geocode] Nominatim request failed for '{query}': {e}")
        return None
    finally:
        if owns_client:
            await client.aclose()

    if not results:
        logger.info(f"[Geocode] Nominatim: no results for '{query}'")
        return None

    top = results[0]
    try:
        return {
            "latitude": float(top["lat"]),
            "longitude": float(top["lon"]),
            "label": top.get("display_name") or query,
            "source": "nominatim",
            "zoom": _zoom_from_nominatim(top),
        }
    except (KeyError, ValueError, TypeError):
        return None


async def geocode_unique_event(
    unique_event_id: int,
    client: httpx.AsyncClient | None = None,
    cache: dict | None = None,
) -> bool:
    """
    Geocode a single UniqueEvent and persist the geolocation fields.

    Sets geocoding_source='none' when no usable result is found so the event is
    not retried on every run. Returns True if coordinates were written.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            text("SELECT * FROM unique_event WHERE id = :id"),
            {"id": unique_event_id},
        )
        event = result.fetchone()

    if not event:
        logger.warning(f"[Geocode] UniqueEvent {unique_event_id} not found")
        return False

    query = build_address_query(event)
    if not query:
        logger.info(f"[Geocode] UniqueEvent {unique_event_id} has no city; marking 'none'")
        await _mark_no_result(unique_event_id)
        return False

    granularity = _input_granularity(event)

    # In-run cache keyed on (query, granularity) avoids duplicate billed calls
    # for identical addresses (e.g. many city-only events in the same city).
    cache_key = (query, granularity)
    fields = cache.get(cache_key) if cache is not None else None
    if fields is None:
        fields = await geocode_address(query, granularity, client=client)
        if cache is not None:
            cache[cache_key] = fields

    if not fields or fields.get("latitude") is None:
        logger.info(f"[Geocode] No usable result for UniqueEvent {unique_event_id} ('{query}')")
        await _mark_no_result(unique_event_id)
        return False

    await _persist_geocode(unique_event_id, fields)
    logger.info(
        f"[Geocode] UniqueEvent {unique_event_id} -> "
        f"({fields['latitude']}, {fields['longitude']}) [{fields['location_precision']}]"
    )
    return True


async def _persist_geocode(unique_event_id: int, fields: dict) -> None:
    async with async_session_maker() as session:
        await session.execute(
            text("""
                UPDATE unique_event
                SET latitude = :latitude,
                    longitude = :longitude,
                    plus_code = :plus_code,
                    place_id = :place_id,
                    formatted_address = :formatted_address,
                    location_precision = :location_precision,
                    geocoding_confidence = :geocoding_confidence,
                    geocoding_source = :geocoding_source,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {
                "id": unique_event_id,
                "latitude": str(Decimal(str(fields["latitude"]))),
                "longitude": str(Decimal(str(fields["longitude"]))),
                "plus_code": fields.get("plus_code"),
                "place_id": fields.get("place_id"),
                "formatted_address": fields.get("formatted_address"),
                "location_precision": fields.get("location_precision"),
                "geocoding_confidence": fields.get("geocoding_confidence"),
                "geocoding_source": fields.get("geocoding_source"),
            },
        )
        await session.commit()


async def _mark_no_result(unique_event_id: int) -> None:
    """Record that geocoding was attempted but produced no usable result."""
    async with async_session_maker() as session:
        await session.execute(
            text("""
                UPDATE unique_event
                SET geocoding_source = :source,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"id": unique_event_id, "source": GEOCODING_SOURCE_NONE},
        )
        await session.commit()


async def geocode_pending(limit: int = 50, delay_seconds: float = 0.05) -> dict:
    """
    Geocode UniqueEvents that have not been geocoded yet.

    Selects events where geocoding_source IS NULL (never attempted) and city is
    present. Runs sequentially with a small delay and a shared in-run cache to
    stay friendly with the Geocoding API and avoid duplicate billed calls.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        logger.warning("[Geocode] GOOGLE_MAPS_API_KEY not set; skipping geocode_pending")
        return {"status": "skipped", "reason": "no_api_key", "geocoded": 0}

    async with async_session_maker() as session:
        result = await session.execute(
            text("""
                SELECT id FROM unique_event
                WHERE geocoding_source IS NULL
                  AND city IS NOT NULL
                ORDER BY id
                LIMIT :limit
            """),
            {"limit": limit},
        )
        event_ids = [row[0] for row in result.fetchall()]

    if not event_ids:
        logger.info("[Geocode] No UniqueEvents pending geocoding")
        return {"status": "completed", "geocoded": 0, "no_result": 0}

    logger.info(f"[Geocode] Geocoding {len(event_ids)} UniqueEvent(s)")

    cache: dict = {}
    geocoded = 0
    no_result = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for i, event_id in enumerate(event_ids):
            try:
                ok = await geocode_unique_event(event_id, client=client, cache=cache)
                if ok:
                    geocoded += 1
                else:
                    no_result += 1
            except Exception as e:  # noqa: BLE001 - keep batch going
                import traceback
                logger.error(
                    f"[Geocode] Error geocoding UniqueEvent {event_id}: {e}\n"
                    f"{traceback.format_exc()}"
                )
                no_result += 1

            if delay_seconds and i < len(event_ids) - 1:
                await asyncio.sleep(delay_seconds)

    logger.info(f"[Geocode] ✅ Geocoded {geocoded}, no_result {no_result}")
    return {
        "status": "completed",
        "geocoded": geocoded,
        "no_result": no_result,
    }
