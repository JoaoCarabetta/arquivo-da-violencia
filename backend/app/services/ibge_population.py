"""
IBGE population data service for rate per 100k calculations.

This module provides functions to:
1. Lookup IBGE municipal codes (code_muni) from city/state names
2. Fetch and cache IBGE population data
3. Calculate rates per 100k population

Note: geobr is an R package. For Python, we use a fixture-based approach for testing
and will load IBGE data from CSV in production.
"""

from typing import Dict, Optional, Tuple
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.ibge_population import IBGEPopulation


# Mapping of (city_name, state_abbrev) to IBGE code_muni
# This is a simplified lookup. In production, this would be loaded from a CSV
# or database table with all Brazilian municipalities.
CITY_CODE_MAPPING: Dict[Tuple[str, str], int] = {
    ("São Paulo", "SP"): 3550308,
    ("Rio de Janeiro", "RJ"): 3304557,
    ("Salvador", "BA"): 2927408,
    ("Brasília", "DF"): 5300108,
    ("Fortaleza", "CE"): 2304400,
    ("Belo Horizonte", "MG"): 3106200,
    ("Manaus", "AM"): 1302603,
    ("Curitiba", "PR"): 4106902,
    ("Recife", "PE"): 2611606,
    ("Porto Alegre", "RS"): 4314902,
    # Add more cities as needed
    ("Bauru", "SP"): 3505708,
}


async def lookup_city_codes(
    cities: list[str],
    states: list[str]
) -> Dict[Tuple[str, str], int]:
    """
    Lookup IBGE municipal codes for a list of (city, state) pairs.
    
    Args:
        cities: List of city names
        states: List of state abbreviations (e.g. "SP", "RJ")
    
    Returns:
        Dictionary mapping (city, state) tuples to IBGE code_muni
    
    Note:
        In production, this would query geobr data or a preloaded lookup table.
        For now, uses a hardcoded mapping for common cities.
    """
    result = {}
    for city, state in zip(cities, states):
        if city and state:
            key = (city, state)
            if key in CITY_CODE_MAPPING:
                result[key] = CITY_CODE_MAPPING[key]
    return result


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
                "year": int
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
                "year": pop.year
            }
    
    return pop_dict


async def load_ibge_population_fixture(session: AsyncSession) -> None:
    """
    Load fixture population data for testing.
    
    This loads a small set of known Brazilian municipalities for testing purposes.
    In production, this would be replaced by a script that loads the full IBGE dataset.
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
            "source": "IBGE Censo 2022"
        },
        {
            "code_muni": 3304557,
            "code_state": "33",
            "name_muni": "Rio de Janeiro",
            "name_state": "Rio de Janeiro",
            "abbrev_state": "RJ",
            "population": 6211423,
            "year": 2022,
            "source": "IBGE Censo 2022"
        },
        {
            "code_muni": 3505708,
            "code_state": "35",
            "name_muni": "Bauru",
            "name_state": "São Paulo",
            "abbrev_state": "SP",
            "population": 379297,
            "year": 2022,
            "source": "IBGE Censo 2022"
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
