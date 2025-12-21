"""City configuration and Brazilian news sources for ingestion."""

# =============================================================================
# City List - Brazilian cities with 500k+ population + all state capitals
# =============================================================================
# Based on 2022 IBGE Census data.
# Each city starts with standard queries.
# When a city hits 100 results, it automatically switches to sharded mode.

CITIES = [
    # ==========================================================================
    # Major Metros (2M+)
    # ==========================================================================
    "São Paulo SP",
    "Rio de Janeiro RJ",
    "Brasília DF",
    "Salvador BA",
    "Fortaleza CE",
    "Belo Horizonte MG",
    "Manaus AM",
    
    # ==========================================================================
    # Large Cities (1M - 2M)
    # ==========================================================================
    "Curitiba PR",
    "Recife PE",
    "Goiânia GO",
    "Belém PA",
    "Porto Alegre RS",
    "Guarulhos SP",
    "Campinas SP",
    "São Luís MA",
    "São Gonçalo RJ",
    
    # ==========================================================================
    # Medium-Large Cities (500k - 1M)
    # ==========================================================================
    "Maceió AL",
    "Duque de Caxias RJ",
    "Campo Grande MS",
    "Natal RN",
    "Teresina PI",
    "São Bernardo do Campo SP",
    "Nova Iguaçu RJ",
    "João Pessoa PB",
    "Santo André SP",
    "São José dos Campos SP",
    "Osasco SP",
    "Ribeirão Preto SP",
    "Jaboatão dos Guararapes PE",
    "Uberlândia MG",
    "Contagem MG",
    "Sorocaba SP",
    "Aracaju SE",
    "Feira de Santana BA",
    "Cuiabá MT",
    "Joinville SC",
    "Aparecida de Goiânia GO",
    "Londrina PR",
    "Juiz de Fora MG",
    "Ananindeua PA",
    "Porto Velho RO",
    "Serra ES",
    "Niterói RJ",
    "Belford Roxo RJ",
    "Campos dos Goytacazes RJ",
    "Caxias do Sul RS",
    
    # ==========================================================================
    # State Capitals (smaller ones not listed above)
    # ==========================================================================
    "Florianópolis SC",  # Capital of Santa Catarina
    "Vitória ES",        # Capital of Espírito Santo
    "Macapá AP",         # Capital of Amapá
    "Boa Vista RR",      # Capital of Roraima
    "Rio Branco AC",     # Capital of Acre
    "Palmas TO",         # Capital of Tocantins
]

# Total: 63 cities (all 27 state capitals + cities with 500k+)


# =============================================================================
# Brazilian News Sources for Sharding
# =============================================================================
# When a city hits the 100-result limit, queries are split by source.
# Each source gets its own query: "{city} when:1h site:{source}"

BRAZILIAN_NEWS_SOURCES = [
    # Major national outlets
    "g1.globo.com",
    "uol.com.br",
    "folha.uol.com.br",
    "estadao.com.br",
    "oglobo.globo.com",
    "r7.com",
    "terra.com.br",
    "metropoles.com",
    "cnn.com.br",
    "band.uol.com.br",
    "jovempan.com.br",
    "correiobraziliense.com.br",
    "gazetadopovo.com.br",
    
    # Regional outlets
    "odia.ig.com.br",        # Rio
    "diariodepernambuco.com.br",  # Pernambuco
    "otempo.com.br",         # Minas Gerais
    "gazetaonline.com.br",   # Espírito Santo
    "acritica.com",          # Amazonas
    "diariodoaco.com.br",    # Minas Gerais interior
]


# =============================================================================
# Rate Limiting Configuration  
# =============================================================================
# Google News RSS limit is ~10-20 requests/minute per IP.
# We use a conservative 12/min to stay safe.

REQUESTS_PER_MINUTE = 12
REQUEST_INTERVAL_SECONDS = 60.0 / REQUESTS_PER_MINUTE  # 5 seconds between requests


# =============================================================================
# Sharding Configuration
# =============================================================================

# Threshold to trigger sharding (when result count >= this value)
SHARDING_THRESHOLD = 100

# Time window for hourly ingestion
DEFAULT_WHEN = "1h"


# =============================================================================
# Capacity Calculation
# =============================================================================
# At 12 req/min = 720 requests/hour
#
# Worst case (all 63 cities need sharding, 19 sources each):
#   63 × 19 = 1,197 queries → would exceed hourly limit
#
# Realistic case (only top 10 cities need sharding):
#   53 standard + (10 × 19) = 243 queries → 20 minutes
#
# Best case (no sharding needed):
#   63 queries → 5 minutes
