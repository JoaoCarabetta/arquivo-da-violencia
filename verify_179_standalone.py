#!/usr/bin/env python3
"""
Standalone verification script for issue #179 improvements.
Tests the key normalization and lookup logic without dependencies.
"""

import unicodedata
import re

# DF (Distrito Federal) administrative regions that are not municipalities
# All map to Brasília 5300108
DF_ADMINISTRATIVE_REGIONS = {
    "taguatinga",
    "ceilandia",
    "samambaia",
    "planaltina",
    "gama",
    "brazlandia",
    "sobradinho",
    "parano",
    "santa maria",
    "sao sebastiao",
    "recanto das emas",
    "lago sul",
    "lago norte",
    "riacho fundo",
    "candangolandia",
    "aguas claras",
    "vicente pires",
    "sudoeste",
    "octogonal",
    "cruzeiro",
    "nucleo bandeirante",
    "guara",
}

# State abbreviation to full name mapping
STATE_FULL_NAMES = {
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
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}

# Reverse mapping: full name to abbreviation (normalized for accent-insensitive matching)
STATE_NAME_TO_ABBREV = {}
for abbrev, full_name in STATE_FULL_NAMES.items():
    # Normalize the full name and store the mapping
    normalized = full_name.lower()
    # Remove accents
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    STATE_NAME_TO_ABBREV[normalized] = abbrev


def normalize_text(text):
    """
    Normalize text for case-insensitive, accent-insensitive comparison.
    """
    if not text:
        return None
    
    # Lowercase
    text = text.lower()
    
    # Remove accents: decompose Unicode, filter out combining marks
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Strip punctuation/hyphens from edges, normalize whitespace
    text = re.sub(r'^[\s\-\.\,]+|[\s\-\.\,]+$', '', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text if text else None


def normalize_state(state):
    """
    Normalize state to abbreviation.
    """
    if not state:
        return None
    
    state = state.strip()
    
    # If it's 2 characters, treat as abbreviation
    if len(state) == 2:
        return state.upper()
    
    # Try to match full name
    normalized = normalize_text(state)
    if normalized and normalized in STATE_NAME_TO_ABBREV:
        return STATE_NAME_TO_ABBREV[normalized]
    
    return None


def point_in_polygon(lat, lng, polygon_coords):
    """
    Check if a point (lat, lng) is inside a polygon using ray casting algorithm.
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


print("=" * 60)
print("Testing normalize_text (case + accent folding)")
print("=" * 60)

test_cases = [
    ("São Paulo", "sao paulo"),
    ("sao paulo", "sao paulo"),
    ("SAO PAULO", "sao paulo"),
    ("Rio de Janeiro", "rio de janeiro"),
    ("  Brasília  ", "brasilia"),
    ("Taguatinga-DF", "taguatinga-df"),  # Hyphens preserved in middle
]

for input_text, expected in test_cases:
    result = normalize_text(input_text)
    status = "✓" if result == expected else "✗"
    print(f"{status} normalize_text({input_text!r}) = {result!r} (expected {expected!r})")

print("\n" + "=" * 60)
print("Testing normalize_state (abbreviation conversion)")
print("=" * 60)

state_cases = [
    ("SP", "SP"),
    ("sp", "SP"),
    ("RJ", "RJ"),
    ("Rio de Janeiro", "RJ"),
    ("rio de janeiro", "RJ"),
    ("São Paulo", "SP"),
    ("Distrito Federal", "DF"),
    ("distrito federal", "DF"),
]

for input_state, expected in state_cases:
    result = normalize_state(input_state)
    status = "✓" if result == expected else "✗"
    print(f"{status} normalize_state({input_state!r}) = {result!r} (expected {expected!r})")

print("\n" + "=" * 60)
print("Testing DF administrative regions")
print("=" * 60)

df_regions = ["taguatinga", "ceilandia", "samambaia", "planaltina"]
for region in df_regions:
    norm = normalize_text(region)
    in_set = norm in DF_ADMINISTRATIVE_REGIONS
    status = "✓" if in_set else "✗"
    print(f"{status} {region!r} normalized to {norm!r} - in DF set: {in_set}")

print("\n" + "=" * 60)
print("Testing point_in_polygon (ray casting)")
print("=" * 60)

# Simple square polygon: [(0,0), (0,10), (10,10), (10,0)]
square = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]

point_tests = [
    ((5, 5), True, "center of square"),
    ((0, 0), True, "corner of square"),
    ((9.9, 9.9), True, "near corner inside"),
    ((15, 15), False, "outside square"),
    ((-1, 5), False, "left of square"),
]

for (lat, lng), expected, desc in point_tests:
    result = point_in_polygon(lat, lng, square)
    status = "✓" if result == expected else "✗"
    print(f"{status} point ({lat}, {lng}) {desc}: {result} (expected {expected})")

print("\n" + "=" * 60)
print("Testing Rio de Janeiro polygon")
print("=" * 60)

# Rio de Janeiro bounding box from fixture
rio_polygon = [
    [-43.7968, -23.0826],
    [-43.0968, -23.0826],
    [-43.0968, -22.7468],
    [-43.7968, -22.7468],
    [-43.7968, -23.0826]
]

# Cristo Redentor coordinates
cristo = (-22.9519, -43.2105)
result = point_in_polygon(cristo[0], cristo[1], rio_polygon)
status = "✓" if result else "✗"
print(f"{status} Cristo Redentor {cristo} in Rio polygon: {result} (expected True)")

# Coordinates outside Rio
outside = (-22.0, -43.0)
result = point_in_polygon(outside[0], outside[1], rio_polygon)
status = "✓" if not result else "✗"
print(f"{status} Point {outside} in Rio polygon: {result} (expected False)")

print("\n" + "=" * 60)
print("All verification tests completed!")
print("=" * 60)
