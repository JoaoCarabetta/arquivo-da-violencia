# Key locations in Rio de Janeiro for violence monitoring
# Curated to focus on high-incident areas and major zones.

ZONES = [
    "Zona Norte RJ",
    "Zona Oeste RJ",
    "Zona Sul RJ",
    "Centro do Rio de Janeiro",
    "Baixada Fluminense" # Often conflated with RJ violence stats
]

FAVELAS_COMMUNITIES = [
    "Rocinha",
    "Complexo do Alemão",
    "Cidade de Deus",
    "Complexo da Maré",
    "Vidigal",
    "Jacarezinho",
    "Mangueira",
    "Vila Cruzeiro",
    "Pavão-Pavãozinho",
    "Morro da Providência",
    "Rio das Pedras",
    "Gardênia Azul",
    "Muzema",
    "Acari",
    "Pedreira",
    "Serrinha"
]

NEIGHBORHOODS = [
    "Copacabana",
    "Ipanema",
    "Barra da Tijuca",
    "Tijuca",
    "Bangu",
    "Realengo",
    "Campo Grande",
    "Santa Cruz",
    "Madureira",
    "Penha",
    "Méier",
    "Irajá",
    "Vicente de Carvalho"
]

# Combined list for aggressive expansion
# We append "RJ" or "Rio de Janeiro" to avoid ambiguity for common names (like "Santa Cruz")
def get_geo_queries():
    queries = []
    
    for zone in ZONES:
        queries.append(f'"{zone}"')
        
    for favela in FAVELAS_COMMUNITIES:
        queries.append(f'"{favela}" Rio de Janeiro')
        
    for hood in NEIGHBORHOODS:
        queries.append(f'"{hood}" Rio de Janeiro')
        
    return queries
