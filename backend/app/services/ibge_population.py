"""
IBGE population data service for rate per 100k calculations.

This module provides functions to:
1. Load IBGE municipal codes from geobr (all BR municipalities)
2. Fetch population data from IBGE SIDRA API (Censo 2022)
3. Cache in database for fast lookups
4. Calculate rates per 100k population

Unit tests use fixture data (no network calls).
Production loads full IBGE dataset once from geobr + SIDRA.
"""

from typing import Dict, Optional, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.models.ibge_population import IBGEPopulation


async def load_ibge_data_from_geobr_and_sidra(
    session: AsyncSession,
    year: int = 2022,
    force_reload: bool = False
) -> None:
    """
    Load full IBGE municipality data from geobr + SIDRA and cache in database.
    
    This is the production path. Loads all ~5,570 Brazilian municipalities:
    1. geobr.read_municipal_seat(year=2022) → codes, names, state info
       Note: geobr.lookup_muni defaults to year=2010 (municipal seats).
       For 2022, we use read_municipal_seat which has 2022 data.
    2. sidrapy.get_table(table_code="4714", ...) → population from Censo 2022
    3. Join by code_muni and store in ibge_population table
    
    Args:
        session: Database session
        year: Census year (default 2022)
        force_reload: If True, reload even if data exists
    
    Note:
        Call this once on deployment or via CLI script:
        python scripts/load_ibge_population.py
        
        Unit tests use load_ibge_population_fixture() instead.
    """
    # Check if data already loaded
    if not force_reload:
        query = select(IBGEPopulation).limit(1)
        result = await session.execute(query)
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(f"IBGE population data already loaded (vintage {existing.year})")
            return
    
    logger.info(f"Loading IBGE municipality codes from geobr (year={year})...")
    
    try:
        import pandas as pd
        
        # Use read_municipal_seat instead of lookup_muni for 2022 data
        # read_municipal_seat has data for 2022, lookup_muni defaults to 2010
        from geobr import read_municipal_seat
        
        # Load all municipal seats with codes
        logger.info("Fetching municipal seat data from geobr...")
        gdf = read_municipal_seat(year=year, verbose=False)
        
        # Drop geometry column to work with regular DataFrame
        munis_df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
        
        logger.info(f"Loaded {len(munis_df)} municipalities from geobr")
        
        # Load population data from SIDRA API
        logger.info("Loading population data from SIDRA API (table 4714)...")
        import sidrapy
        
        pop_df = sidrapy.get_table(
            table_code="4714",
            territorial_level="6",  # Municipality level
            ibge_territorial_code="all",
            variable="93",  # Population variable
            period=str(year),
        )
        
        # SIDRA columns: D1C (code_muni), D1N (name), V (value/population)
        # Clean and prepare population data
        pop_df = pop_df[['D1C', 'D1N', 'V']].copy()
        pop_df.columns = ['code_muni_str', 'name_muni_sidra', 'population_str']
        pop_df['code_muni'] = pd.to_numeric(pop_df['code_muni_str'], errors='coerce')
        pop_df['population'] = pd.to_numeric(pop_df['population_str'], errors='coerce')
        pop_df = pop_df.dropna(subset=['code_muni', 'population'])
        pop_df['code_muni'] = pop_df['code_muni'].astype(int)
        pop_df['population'] = pop_df['population'].astype(int)
        
        logger.info(f"Loaded {len(pop_df)} municipality populations from SIDRA")
        
        # Join geobr codes with SIDRA populations
        merged = munis_df.merge(
            pop_df[['code_muni', 'population']],
            on='code_muni',
            how='left'
        )
        
        # Store in database
        count = 0
        for _, row in merged.iterrows():
            if pd.isna(row.get('population')):
                continue  # Skip municipalities without population data
            
            pop = IBGEPopulation(
                code_muni=int(row['code_muni']),
                code_state=str(int(float(row['code_state']))).zfill(2),
                name_muni=str(row['name_muni']),
                name_state=str(row['name_state']) if pd.notna(row.get('name_state')) else None,
                abbrev_state=str(row['abbrev_state']) if pd.notna(row.get('abbrev_state')) else None,
                population=int(row['population']),
                year=year,
                source=f"IBGE Censo {year} (geobr + SIDRA)"
            )
            session.add(pop)
            count += 1
        
        await session.commit()
        logger.info(f"Stored {count} municipalities with population data in database")
        
    except ImportError as e:
        logger.error(f"Missing required package: {e}. Install with: pip install geobr sidrapy")
        raise
    except Exception as e:
        logger.error(f"Failed to load IBGE data: {e}")
        raise


async def lookup_city_codes(
    session: AsyncSession,
    cities: list[str],
    states: list[str]
) -> Dict[Tuple[str, str], int]:
    """
    Lookup IBGE municipal codes for a list of (city, state) pairs.
    
    Queries the ibge_population table (loaded from geobr).
    No hardcoded mapping - works for any city in the IBGE database.
    
    Args:
        session: Database session
        cities: List of city names
        states: List of state abbreviations (e.g. "SP", "RJ")
    
    Returns:
        Dictionary mapping (city, state) tuples to IBGE code_muni
    """
    if not cities:
        return {}
    
    # Build lookup of (city, state) pairs
    city_state_pairs = [(city, state) for city, state in zip(cities, states) if city and state]
    if not city_state_pairs:
        return {}
    
    # Query database for matching municipalities
    # Try exact match first, could add fuzzy matching later
    result = {}
    
    for city, state in city_state_pairs:
        query = select(IBGEPopulation).where(
            IBGEPopulation.name_muni == city,
            IBGEPopulation.abbrev_state == state
        )
        db_result = await session.execute(query)
        pop = db_result.scalar_one_or_none()
        
        if pop and pop.code_muni:
            result[(city, state)] = pop.code_muni
    
    return result


async def lookup_state_codes(
    session: AsyncSession,
    states: list[str]
) -> Dict[str, str]:
    """
    Lookup IBGE state codes for a list of state abbreviations.
    
    Args:
        session: Database session
        states: List of state abbreviations (e.g. "SP", "RJ")
    
    Returns:
        Dictionary mapping state abbreviation to code_state (e.g. "SP" → "35")
    """
    if not states:
        return {}
    
    result = {}
    
    for state in states:
        if not state:
            continue
        
        # Query for any municipality in that state to get code_state
        query = select(IBGEPopulation).where(
            IBGEPopulation.abbrev_state == state
        ).limit(1)
        
        db_result = await session.execute(query)
        pop = db_result.scalar_one_or_none()
        
        if pop and pop.code_state:
            result[state] = pop.code_state
    
    return result


async def get_state_populations(
    session: AsyncSession,
    code_states: list[str]
) -> Dict[str, dict]:
    """
    Get aggregated state populations by summing all municipalities in each state.
    
    Args:
        session: Database session
        code_states: List of IBGE state codes (e.g. ["35", "33"])
    
    Returns:
        Dictionary mapping code_state to population data:
        {
            "35": {
                "name": "São Paulo",
                "population": 44411238,
                "year": 2022
            }
        }
    """
    if not code_states:
        return {}
    
    # Query all municipalities for these states
    query = select(IBGEPopulation).where(
        IBGEPopulation.code_state.in_(code_states)
    )
    result = await session.execute(query)
    populations = result.scalars().all()
    
    # Aggregate by state
    state_data = {}
    for pop in populations:
        if not pop.code_state:
            continue
        
        if pop.code_state not in state_data:
            state_data[pop.code_state] = {
                "name": pop.name_state or pop.abbrev_state,
                "population": 0,
                "year": pop.year
            }
        
        state_data[pop.code_state]["population"] += pop.population
    
    return state_data


async def get_ibge_populations(
    session: AsyncSession,
    code_munis: list[int]
) -> Dict[int, dict]:
    """
    Get IBGE population data for a list of municipal codes.
    
    Args:
        session: Database session
        code_munis: List of IBGE municipal codes
    
    Returns:
        Dictionary mapping code_muni to population data:
        {
            code_muni: {
                "name": str,
                "population": int,
                "year": int,
                "abbrev_state": str (e.g. "SP", "RJ")
            }
        }
    """
    if not code_munis:
        return {}
    
    # Query cached population data
    query = select(IBGEPopulation).where(
        IBGEPopulation.code_muni.in_(code_munis)
    )
    result = await session.execute(query)
    populations = result.scalars().all()
    
    # Build result dictionary
    pop_dict = {}
    for pop in populations:
        if pop.code_muni:
            pop_dict[pop.code_muni] = {
                "name": pop.name_muni,
                "population": pop.population,
                "year": pop.year,
                "abbrev_state": pop.abbrev_state
            }
    
    return pop_dict


async def load_ibge_population_fixture(session: AsyncSession) -> None:
    """
    Load fixture population data for testing.
    
    This loads a small set of known Brazilian municipalities for testing purposes.
    In production, use load_ibge_data_from_geobr_and_sidra() instead.
    
    Includes São Paulo, Rio, Bauru, and Campinas (to prove lookup isn't a hardcoded allowlist).
    """
    # Sample data from IBGE Censo 2022
    fixtures = [
        {
            "code_muni": 3550308,
            "code_state": "35",
            "name_muni": "São Paulo",
            "name_state": "São Paulo",
            "abbrev_state": "SP",
            "population": 11451245,
            "year": 2022,
            "source": "IBGE Censo 2022 (fixture)"
        },
        {
            "code_muni": 3304557,
            "code_state": "33",
            "name_muni": "Rio de Janeiro",
            "name_state": "Rio de Janeiro",
            "abbrev_state": "RJ",
            "population": 6211423,
            "year": 2022,
            "source": "IBGE Censo 2022 (fixture)"
        },
        {
            "code_muni": 3505708,
            "code_state": "35",
            "name_muni": "Bauru",
            "name_state": "São Paulo",
            "abbrev_state": "SP",
            "population": 379297,
            "year": 2022,
            "source": "IBGE Censo 2022 (fixture)"
        },
        {
            # Extra city NOT in any hardcoded list - proves lookup works via DB
            "code_muni": 3509502,
            "code_state": "35",
            "name_muni": "Campinas",
            "name_state": "São Paulo",
            "abbrev_state": "SP",
            "population": 1213792,
            "year": 2022,
            "source": "IBGE Censo 2022 (fixture)"
        },
    ]
    
    for fixture in fixtures:
        # Check if already exists
        query = select(IBGEPopulation).where(
            IBGEPopulation.code_muni == fixture["code_muni"]
        )
        result = await session.execute(query)
        existing = result.scalar_one_or_none()
        
        if not existing:
            pop = IBGEPopulation(**fixture)
            session.add(pop)
    
    await session.commit()


def calculate_rate_per_100k(victim_count: int, population: int) -> float:
    """
    Calculate the rate per 100,000 population.
    
    Args:
        victim_count: Number of victims
        population: Total population
    
    Returns:
        Rate per 100,000 population, rounded to 2 decimal places
    """
    if population <= 0:
        return 0.0
    return round((victim_count / population) * 100000, 2)
