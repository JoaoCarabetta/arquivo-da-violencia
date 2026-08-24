"""Country registry for multi-country pipeline support.

This module provides a centralized registry of all countries supported by the pipeline.
Each country configuration includes:
- ISO 3166-1 alpha-2 code
- Google News parameters (hl, gl, ceid)
- Primary language
- Major cities for ingestion (capitals + large metros)
- News outlet domains for query sharding
- Homicide query terms
- Geocoding parameters (region code, language)
"""

from dataclasses import dataclass
from typing import Literal


# ============================================================================
# Type definitions
# ============================================================================

CountryCode = Literal["AR", "BO", "BR", "CL", "CO", "EC", "GY", "PY", "PE", "SR", "UY", "VE"]


# ============================================================================
# Country Configuration Data Class
# ============================================================================

@dataclass
class CountryConfig:
    """Configuration for a single country's pipeline behavior."""
    
    # Identity
    code: CountryCode
    name: str
    
    # Google News RSS parameters
    google_news_hl: str  # Language header (e.g., "pt-BR", "es-AR")
    google_news_gl: str  # Geographic location (e.g., "BR", "AR")
    google_news_ceid: str  # Edition ID (e.g., "BR:pt-419", "AR:es-419")
    
    # Primary language for content (ISO 639-1)
    language: str  # "pt", "es", "en", "nl"
    
    # Cities for ingestion (capitals + major metros)
    # Format varies by country needs; include region/state when helpful for disambiguation
    cities: list[str]
    
    # News outlets for query sharding (when a city hits 100 results)
    outlets: list[str]
    
    # Homicide query terms in local language
    query_terms: list[str]
    
    # Geocoding configuration
    geocode_region: str  # Google Geocoding API region bias (usually same as code)
    geocode_language: str  # Geocoding result language (ISO 639-1)


# ============================================================================
# Argentina (AR)
# ============================================================================

ARGENTINA_CONFIG = CountryConfig(
    code="AR",
    name="Argentina",
    google_news_hl="es-AR",
    google_news_gl="AR",
    google_news_ceid="AR:es-419",
    language="es",
    cities=[
        "Buenos Aires",
        "Córdoba",
        "Rosario",
        "Mendoza",
        "San Miguel de Tucumán",
        "La Plata",
        "Mar del Plata",
        "Salta",
        "Santa Fe",
        "San Juan",
        "Resistencia",
        "Corrientes",
        "Posadas",
        "Neuquén",
        "Bahía Blanca",
    ],
    outlets=[
        "clarin.com",
        "lanacion.com.ar",
        "infobae.com",
        "pagina12.com.ar",
        "ambito.com",
        "perfil.com",
        "cronica.com.ar",
        "ole.com.ar",
        "lacapital.com.ar",
        "losandes.com.ar",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "femicidio",
        "feminicidio",
        "tiroteo",
        "balacera",
        "muerte violenta",
        "crimen",
    ],
    geocode_region="ar",
    geocode_language="es",
)


# ============================================================================
# Bolivia (BO)
# ============================================================================

BOLIVIA_CONFIG = CountryConfig(
    code="BO",
    name="Bolivia",
    google_news_hl="es-BO",
    google_news_gl="BO",
    google_news_ceid="BO:es-419",
    language="es",
    cities=[
        "La Paz",
        "Santa Cruz de la Sierra",
        "Cochabamba",
        "Sucre",
        "Oruro",
        "Tarija",
        "Potosí",
        "Trinidad",
    ],
    outlets=[
        "lostiempos.com",
        "eldeber.com.bo",
        "paginasiete.bo",
        "erbol.com.bo",
        "opinion.com.bo",
        "eldiario.net",
        "cambio.bo",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "feminicidio",
        "muerte violenta",
        "tiroteo",
        "crimen",
    ],
    geocode_region="bo",
    geocode_language="es",
)


# ============================================================================
# Brazil (BR)
# ============================================================================

BRAZIL_CONFIG = CountryConfig(
    code="BR",
    name="Brasil",
    google_news_hl="pt-BR",
    google_news_gl="BR",
    google_news_ceid="BR:pt-419",
    language="pt",
    cities=[
        # Major Metros (2M+)
        "São Paulo SP",
        "Rio de Janeiro RJ",
        "Brasília DF",
        "Salvador BA",
        "Fortaleza CE",
        "Belo Horizonte MG",
        "Manaus AM",
        # Large Cities (1M - 2M)
        "Curitiba PR",
        "Recife PE",
        "Goiânia GO",
        "Belém PA",
        "Porto Alegre RS",
        "Guarulhos SP",
        "Campinas SP",
        "São Luís MA",
        "São Gonçalo RJ",
        # Medium-Large Cities (500k - 1M)
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
        # State Capitals (smaller ones)
        "Florianópolis SC",
        "Vitória ES",
        "Macapá AP",
        "Boa Vista RR",
        "Rio Branco AC",
        "Palmas TO",
    ],
    outlets=[
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
        "ig.com.br",
        "noticias.uol.com.br",
        "record.tv.br",
        "extra.globo.com",
        "otempo.com.br",
        "em.com.br",
        "correiobraziliense.com.br",
        "gazetadopovo.com.br",
        "diariodepernambuco.com.br",
    ],
    query_terms=[
        # Brazilian Portuguese terms (broad, no explicit terms needed - implicit in context)
    ],
    geocode_region="br",
    geocode_language="pt",
)


# ============================================================================
# Chile (CL)
# ============================================================================

CHILE_CONFIG = CountryConfig(
    code="CL",
    name="Chile",
    google_news_hl="es-CL",
    google_news_gl="CL",
    google_news_ceid="CL:es-419",
    language="es",
    cities=[
        # Major Metros (1M+)
        "Santiago Metropolitana",
        "Puente Alto Metropolitana",
        "Maipú Metropolitana",
        "La Florida Metropolitana",
        # Large Cities (200k - 1M)
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
        # Regional Capitals (smaller)
        "Arica Arica y Parinacota",
        "La Serena Coquimbo",
        "Punta Arenas Magallanes",
        "Coyhaique Aysén",
    ],
    outlets=[
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
        "australvaldivia.cl",
        "elsur.cl",
        "australtemuco.cl",
        "mercuriovalpo.cl",
        "soychile.cl",
        "elllanquihue.cl",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "femicidio",
        "feminicidio",
        "balacera",
        "tiroteo",
        "robo con homicidio",
        "muerte violenta",
        "operativo policial",
        "carabineros disparo",
    ],
    geocode_region="cl",
    geocode_language="es",
)


# ============================================================================
# Colombia (CO)
# ============================================================================

COLOMBIA_CONFIG = CountryConfig(
    code="CO",
    name="Colombia",
    google_news_hl="es-CO",
    google_news_gl="CO",
    google_news_ceid="CO:es-419",
    language="es",
    cities=[
        "Bogotá",
        "Medellín",
        "Cali",
        "Barranquilla",
        "Cartagena",
        "Cúcuta",
        "Bucaramanga",
        "Pereira",
        "Santa Marta",
        "Ibagué",
        "Pasto",
        "Manizales",
        "Villavicencio",
        "Armenia",
    ],
    outlets=[
        "eltiempo.com",
        "elespectador.com",
        "semana.com",
        "caracol.com.co",
        "rcnradio.com",
        "pulzo.com",
        "bluradio.com",
        "elcolombiano.com",
        "laopinion.com.co",
        "vanguardia.com",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "feminicidio",
        "sicariato",
        "masacre",
        "balacera",
        "tiroteo",
        "muerte violenta",
        "crimen",
    ],
    geocode_region="co",
    geocode_language="es",
)


# ============================================================================
# Ecuador (EC)
# ============================================================================

ECUADOR_CONFIG = CountryConfig(
    code="EC",
    name="Ecuador",
    google_news_hl="es-EC",
    google_news_gl="EC",
    google_news_ceid="EC:es-419",
    language="es",
    cities=[
        "Guayaquil",
        "Quito",
        "Cuenca",
        "Santo Domingo",
        "Machala",
        "Durán",
        "Manta",
        "Portoviejo",
        "Ambato",
        "Riobamba",
    ],
    outlets=[
        "eluniverso.com",
        "elcomercio.com",
        "expreso.ec",
        "teleamazonas.com",
        "ecuavisa.com",
        "metroecuador.com.ec",
        "primicias.ec",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "feminicidio",
        "sicariato",
        "balacera",
        "tiroteo",
        "muerte violenta",
        "crimen",
    ],
    geocode_region="ec",
    geocode_language="es",
)


# ============================================================================
# Guyana (GY)
# ============================================================================

GUYANA_CONFIG = CountryConfig(
    code="GY",
    name="Guyana",
    google_news_hl="en-GY",
    google_news_gl="GY",
    google_news_ceid="GY:en",
    language="en",
    cities=[
        "Georgetown",
        "Linden",
        "New Amsterdam",
    ],
    outlets=[
        "stabroeknews.com",
        "kaieteurnewsonline.com",
        "demerarawaves.com",
        "guyanatimesgy.com",
    ],
    query_terms=[
        "murder",
        "homicide",
        "killing",
        "shooting",
        "violent death",
        "gunfire",
    ],
    geocode_region="gy",
    geocode_language="en",
)


# ============================================================================
# Paraguay (PY)
# ============================================================================

PARAGUAY_CONFIG = CountryConfig(
    code="PY",
    name="Paraguay",
    google_news_hl="es-PY",
    google_news_gl="PY",
    google_news_ceid="PY:es-419",
    language="es",
    cities=[
        "Asunción",
        "Ciudad del Este",
        "San Lorenzo",
        "Luque",
        "Capiatá",
        "Encarnación",
    ],
    outlets=[
        "abc.com.py",
        "ultimahora.com",
        "lanacion.com.py",
        "hoy.com.py",
        "extra.com.py",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "feminicidio",
        "tiroteo",
        "balacera",
        "muerte violenta",
        "sicariato",
    ],
    geocode_region="py",
    geocode_language="es",
)


# ============================================================================
# Peru (PE)
# ============================================================================

PERU_CONFIG = CountryConfig(
    code="PE",
    name="Perú",
    google_news_hl="es-PE",
    google_news_gl="PE",
    google_news_ceid="PE:es-419",
    language="es",
    cities=[
        "Lima",
        "Arequipa",
        "Trujillo",
        "Chiclayo",
        "Piura",
        "Cusco",
        "Iquitos",
        "Huancayo",
        "Tacna",
        "Callao",
    ],
    outlets=[
        "elcomercio.pe",
        "larepublica.pe",
        "rpp.pe",
        "gestion.pe",
        "peru21.pe",
        "andina.pe",
        "exitosanoticias.pe",
        "elperuano.pe",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "feminicidio",
        "sicariato",
        "balacera",
        "tiroteo",
        "muerte violenta",
        "crimen",
    ],
    geocode_region="pe",
    geocode_language="es",
)


# ============================================================================
# Suriname (SR)
# ============================================================================

SURINAME_CONFIG = CountryConfig(
    code="SR",
    name="Suriname",
    google_news_hl="nl-SR",
    google_news_gl="SR",
    google_news_ceid="SR:nl",
    language="nl",
    cities=[
        "Paramaribo",
        "Lelydorp",
        "Nieuw Nickerie",
    ],
    outlets=[
        "starnieuws.com",
        "dbsuriname.com",
        "waterkant.net",
    ],
    query_terms=[
        "moord",
        "doodslag",
        "schietpartij",
        "gewelddadige dood",
    ],
    geocode_region="sr",
    geocode_language="nl",
)


# ============================================================================
# Uruguay (UY)
# ============================================================================

URUGUAY_CONFIG = CountryConfig(
    code="UY",
    name="Uruguay",
    google_news_hl="es-UY",
    google_news_gl="UY",
    google_news_ceid="UY:es-419",
    language="es",
    cities=[
        "Montevideo",
        "Salto",
        "Ciudad de la Costa",
        "Paysandú",
        "Maldonado",
    ],
    outlets=[
        "elpais.com.uy",
        "elobservador.com.uy",
        "montevideo.com.uy",
        "republica.com.uy",
        "subrayado.com.uy",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "femicidio",
        "tiroteo",
        "balacera",
        "muerte violenta",
    ],
    geocode_region="uy",
    geocode_language="es",
)


# ============================================================================
# Venezuela (VE)
# ============================================================================

VENEZUELA_CONFIG = CountryConfig(
    code="VE",
    name="Venezuela",
    google_news_hl="es-VE",
    google_news_gl="VE",
    google_news_ceid="VE:es-419",
    language="es",
    cities=[
        "Caracas",
        "Maracaibo",
        "Valencia",
        "Barquisimeto",
        "Maracay",
        "Ciudad Guayana",
        "Barcelona",
        "Maturín",
        "Cumaná",
    ],
    outlets=[
        "eluniversal.com",
        "elimpulso.com",
        "talcualdigital.com",
        "runrun.es",
        "noticiaaldia.com",
    ],
    query_terms=[
        "homicidio",
        "asesinato",
        "feminicidio",
        "sicariato",
        "ajusticiamiento",
        "balacera",
        "tiroteo",
        "muerte violenta",
    ],
    geocode_region="ve",
    geocode_language="es",
)


# ============================================================================
# Country Registry
# ============================================================================

# All country configurations
COUNTRY_CONFIGS: dict[CountryCode, CountryConfig] = {
    "AR": ARGENTINA_CONFIG,
    "BO": BOLIVIA_CONFIG,
    "BR": BRAZIL_CONFIG,
    "CL": CHILE_CONFIG,
    "CO": COLOMBIA_CONFIG,
    "EC": ECUADOR_CONFIG,
    "GY": GUYANA_CONFIG,
    "PY": PARAGUAY_CONFIG,
    "PE": PERU_CONFIG,
    "SR": SURINAME_CONFIG,
    "UY": URUGUAY_CONFIG,
    "VE": VENEZUELA_CONFIG,
}

# List of all supported country codes
ALL_COUNTRIES: list[CountryCode] = list(COUNTRY_CONFIGS.keys())


# ============================================================================
# Helper Functions
# ============================================================================

def get_country_config(country_code: CountryCode) -> CountryConfig:
    """Get the configuration for a specific country."""
    return COUNTRY_CONFIGS[country_code]


def get_country_name(country_code: CountryCode) -> str:
    """Get the human-readable name for a country code."""
    return COUNTRY_CONFIGS[country_code].name


def is_valid_country(country_code: str) -> bool:
    """Check if a country code is supported."""
    return country_code in COUNTRY_CONFIGS
