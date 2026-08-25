"""
Municipality code backfill service for existing UniqueEvents (issue #174).

This module provides functions to backfill IBGE municipality codes for existing
UniqueEvents that were geocoded before the municipality_code field existed.

Only Brazilian municipalities get codes. Ambiguous city names (no state) are
skipped - we do not guess.
"""

from typing import Dict
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text
from loguru import logger

from app.services.ibge_population import lookup_city_codes


async def backfill_municipality_codes(
    session: AsyncSession,
    limit: int | None = None
) -> Dict[str, int]:
    """
    Backfill municipality_code for existing UniqueEvents that lack it.
    
    Only updates events where:
    - municipality_code IS NULL
    - country is BR, Brasil, or NULL (default BR)
    - city AND state are both present (unambiguous)
    - city+state uniquely resolve to an IBGE code
    
    Does NOT guess codes for:
    - Events with city but no state (ambiguous)
    - Non-Brazilian events (Chile, etc.)
    - Events where the city name is not in the IBGE database
    
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
    # Find events that need codes: Brazilian events with city+state but no code
    query = text("""
        SELECT id, city, state, country
        FROM unique_event
        WHERE municipality_code IS NULL
          AND (country IN ('BR', 'Brasil') OR country IS NULL)
          AND city IS NOT NULL
          AND state IS NOT NULL
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
    
    # Build unique list of (city, state) pairs to lookup
    city_state_pairs = set()
    for event in events:
        city = event[1]
        state = event[2]
        if city and state:
            city_state_pairs.add((city, state))
    
    # Batch lookup all codes
    cities = [pair[0] for pair in city_state_pairs]
    states = [pair[1] for pair in city_state_pairs]
    code_map = await lookup_city_codes(session, cities=cities, states=states)
    
    logger.info(f"[Backfill] Resolved {len(code_map)} municipality codes")
    
    # Update events
    updated = 0
    not_found = 0
    
    for event in events:
        event_id = event[0]
        city = event[1]
        state = event[2]
        
        code = code_map.get((city, state))
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
    
    logger.info(f"[Backfill] ✅ Updated {updated} events, {not_found} not found in IBGE database")
    
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
    
    # Events with no state
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
