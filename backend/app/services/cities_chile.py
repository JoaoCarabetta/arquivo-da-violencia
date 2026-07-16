"""Chilean cities and news sources for ingestion.

This module mirrors cities.py but for Chile, providing:
- Major Chilean cities for ingestion (500k+ population + all regional capitals)
- Chilean news sources for query sharding
- Chilean-specific Google News parameters
"""

# =============================================================================
# Chilean City List - cities with 200k+ population + all regional capitals
# =============================================================================
# Based on 2017 Chilean Census + regional capitals
# Format: "City Region" for Google News queries

CHILEAN_CITIES = [
    # ==========================================================================
    # Major Metros (1M+)
    # ==========================================================================
    "Santiago Metropolitana",
    "Puente Alto Metropolitana",
    "Maipú Metropolitana",
    "La Florida Metropolitana",
    
    # ==========================================================================
    # Large Cities (200k - 1M)
    # ==========================================================================
    "Antofagasta Antofagasta",
    "Viña del Mar Valparaíso",
    "Valparaíso Valparaíso",
    "Talcahuano Biobío",
    "San Bernardo Metropolitana",
    "Temuco Araucanía",
    "Iquique Tarapacá",
    "Concepción Biobío",
    "Rancagua O'Higgins",
    "Talca Maule",
    "Coquimbo Coquimbo",
    "Puerto Montt Los Lagos",
    "Chillán Ñuble",
    "Los Ángeles Biobío",
    "Calama Antofagasta",
    "Copiapó Atacama",
    "Osorno Los Lagos",
    "Valdivia Los Ríos",
    "Quilpué Valparaíso",
    
    # ==========================================================================
    # Regional Capitals (smaller ones not listed above)
    # ==========================================================================
    "Arica Arica y Parinacota",
    "La Serena Coquimbo",
    "Punta Arenas Magallanes",
    "Coyhaique Aysén",
]

# Total: 27 cities (all 16 regional capitals + major population centers)

# =============================================================================
# Chilean News Sources for Sharding
# =============================================================================
# When a city hits the 100-result limit, queries are split by source.
# Each source gets its own query: "{city} when:1h site:{source}"

CHILEAN_NEWS_SOURCES = [
    # Major national outlets
    "emol.com",
    "latercera.com",
    "elmostrador.cl",
    "biobiochile.cl",
    "24horas.cl",
    "meganoticias.cl",
    "t13.cl",
    "chvnoticias.cl",
    "cnnchile.com",
    "df.cl",
    "cooperativa.cl",
    "adnradio.cl",
    
    # Regional outlets
    "australvaldivia.cl",    # Los Ríos
    "elsur.cl",              # Concepción
    "australtemuco.cl",      # Araucanía
    "mercuriovalpo.cl",      # Valparaíso
    "soychile.cl",           # Nacional
    "elllanquihue.cl",       # Puerto Montt
]

# =============================================================================
# Google News RSS Configuration for Chile
# =============================================================================

CHILE_GOOGLE_NEWS_PARAMS = {
    "hl": "es-CL",      # Language: Spanish (Chile)
    "gl": "CL",         # Country: Chile
    "ceid": "CL:es-419", # Edition: Chile Spanish (Latin America)
}

# =============================================================================
# Chilean Violence Terms for Queries
# =============================================================================
# Spanish terms for violent deaths in Chilean context

CHILEAN_QUERY_TERMS = [
    "homicidio",
    "asesinato",
    "femicidio",
    "feminicidio",
    "balacera",
    "tiroteo",
    "robo con homicidio",  # latrocinio equivalent
    "muerte violenta",
    "operativo policial",
    "carabineros disparo",
]
