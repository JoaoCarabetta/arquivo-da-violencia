"""Published at /llms.txt for agents and Claude Desktop."""

LLMS_TXT = """# Arquivo da Violência

Public HTTP API for news-derived violent-death events in Brazil.
This is a journalistic archive, not official SIM/FBSP statistics.

## Discovery

- OpenAPI: https://arquivodaviolencia.com.br/api/openapi.json
- Interactive docs: https://arquivodaviolencia.com.br/api/docs
- Use this API: https://arquivodaviolencia.com.br/usar-api
- Methodology: https://arquivodaviolencia.com.br/metodologia
- Ask (one-shot): POST https://arquivodaviolencia.com.br/api/public/ask

Claude Desktop: add a custom connector from the OpenAPI URL. No MCP required.
CORS is open on /api/public/* (read + ask). Attribute Arquivo da Violência
and link the methodology page.

## Tools

- GET /api/public/geocode?q= — resolve a street/city/CEP to lat/lng
- GET /api/public/nearby?lat=&lng=&radius_km=5&days=365 — nearby summary + events
  (each event has location_precision; city_center is not rooftop accuracy)
- GET /api/public/stats/series?state=CE&subtype=feminicidio&interval=week&days=365
  — current vs previous window, direction up/down/flat/insufficient
- GET /api/public/events — filters: city, state, type/subtype, date_from, date_to
- POST /api/public/ask — {"question": "..."} returns answer, caveats, query, data, citations

## Example questions

1. Crimes near Rua Umari 28, Rio
   → GET /api/public/geocode?q=Rua+Umari+28,+Rio+de+Janeiro
   → GET /api/public/nearby with the returned coordinates
2. O feminicídio está subindo no Ceará?
   → GET /api/public/stats/series?state=CE&subtype=feminicidio&interval=week&days=365
"""
