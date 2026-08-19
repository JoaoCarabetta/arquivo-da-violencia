"""Country, region, and city definitions for multi-country support.

This module provides geography data for Brazil and Chile, including:
- ISO country codes
- Administrative regions (states/UFs for BR, regiones for CL)
- Major cities for ingestion
"""

from typing import Literal

# ============================================================================
# Country codes (ISO 3166-1 alpha-2)
# ============================================================================

Country = Literal["BR", "CL"]

COUNTRIES: list[Country] = ["BR", "CL"]

COUNTRY_NAMES = {
    "BR": "Brasil",
    "CL": "Chile",
}

# ============================================================================
# Brazilian Geography
# ============================================================================

# Brazilian states (Unidades Federativas)
BRAZILIAN_STATES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO"
]

BRAZILIAN_STATE_NAMES = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RO": "Rondônia",
    "RR": "Roraima",
    "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina",
    "SE": "Sergipe",
    "SP": "São Paulo",
    "TO": "Tocantins",
}

# ============================================================================
# Chilean Geography
# ============================================================================

# Chilean regions (regiones)
CHILEAN_REGIONS = [
    "Arica y Parinacota",
    "Tarapacá",
    "Antofagasta",
    "Atacama",
    "Coquimbo",
    "Valparaíso",
    "Metropolitana",
    "O'Higgins",
    "Maule",
    "Ñuble",
    "Biobío",
    "Araucanía",
    "Los Ríos",
    "Los Lagos",
    "Aysén",
    "Magallanes",
]

# Region codes (Roman numerals traditionally used in Chile)
CHILEAN_REGION_CODES = {
    "Arica y Parinacota": "XV",
    "Tarapacá": "I",
    "Antofagasta": "II",
    "Atacama": "III",
    "Coquimbo": "IV",
    "Valparaíso": "V",
    "Metropolitana": "RM",
    "O'Higgins": "VI",
    "Maule": "VII",
    "Ñuble": "XVI",
    "Biobío": "VIII",
    "Araucanía": "IX",
    "Los Ríos": "XIV",
    "Los Lagos": "X",
    "Aysén": "XI",
    "Magallanes": "XII",
}

# Reverse lookup: code -> name
CHILEAN_REGION_NAMES = {v: k for k, v in CHILEAN_REGION_CODES.items()}

# ============================================================================
# Unified region handling (for API filters and stats)
# ============================================================================

def get_regions_for_country(country: Country) -> list[str]:
    """Return list of region codes/names for a country."""
    if country == "BR":
        return BRAZILIAN_STATES
    elif country == "CL":
        return CHILEAN_REGIONS
    return []


def get_region_name(country: Country, code: str) -> str:
    """Get human-readable region name for a code."""
    if country == "BR":
        return BRAZILIAN_STATE_NAMES.get(code, code)
    elif country == "CL":
        return CHILEAN_REGION_NAMES.get(code, code)
    return code


def normalize_region_identifier(country: Country, value: str) -> str:
    """Normalize region identifier to canonical form for storage.
    
    For BR: keeps UF codes (SP, RJ, etc.)
    For CL: converts Roman numerals to region names or keeps region names.
    """
    if country == "BR":
        return value.upper()
    elif country == "CL":
        # Accept both codes (RM, XV, etc.) and full names
        if value in CHILEAN_REGION_NAMES:
            return CHILEAN_REGION_NAMES[value]
        return value
    return value
