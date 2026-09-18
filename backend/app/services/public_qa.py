"""Public Q&A helpers: trend series, nearby summaries, and POST /ask.

The LLM (when configured) only picks tools and writes prose from JSON those
tools return. Heuristics cover the same path so tests and keyless deploys work.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.config import get_settings
from app.geography import BRAZILIAN_STATE_NAMES
from app.models.unique_event import UniqueEvent
from app.services.public_filters import apply_public_incident_filter, homicide_type_filter
from app.taxonomy import SUBTYPE_LABELS_PT, SUBTYPES_BY_FAMILY

PUBLIC_SITE_URL = "https://arquivodaviolencia.com.br"
METHODOLOGY_URL = f"{PUBLIC_SITE_URL}/metodologia"
PUBLIC_SOURCE = "Arquivo da Violência"
PUBLIC_WINDOW_DAYS = 365

TREND_CAVEATS = [
    "Dados derivados de notícias indexadas neste arquivo, não são estatísticas oficiais (SIM/FBSP).",
    "Há viés de cobertura jornalística: o que não é noticiado não entra no arquivo.",
    "A janela pública padrão é de 365 dias; compare apenas janelas iguais.",
]

PLACE_CAVEATS = [
    "Um raio de 5 km em torno de um endereço não significa que os crimes ocorreram nessa rua.",
    "A maioria dos pontos tem precisão de centro da cidade ou do bairro, não de telhado.",
    "Dados derivados de notícias neste arquivo, não estatísticas oficiais.",
]

AskIntent = Literal["place", "trend", "event_lookup"]
SeriesDirection = Literal["up", "down", "flat", "insufficient"]
SeriesInterval = Literal["day", "week", "month"]


class AskRequest(BaseModel):
    """One-shot question for the public archive."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=[
            "Rua Umari 28, Rio de Janeiro",
            "O feminicídio está subindo no Ceará?",
        ],
        description="Pergunta em linguagem natural (pt-BR ou en).",
    )


class AskPlan(BaseModel):
    """Tool plan produced by heuristics or the LLM. Never contains SQL."""

    intent: AskIntent
    place_query: str | None = None
    state: str | None = None
    subtype: str | None = None
    days: int = PUBLIC_WINDOW_DAYS
    radius_km: float = 5.0
    search: str | None = None
    event_id: int | None = None


_HOMICIDIO_SUBTYPES = SUBTYPES_BY_FAMILY["homicidio"]

_TREND_RE = re.compile(
    r"subindo|caindo|aument|diminu|tend[eê]ncia|going up|going down|\btrend\b|"
    r"cresce|caiu|subiu|mais casos|menos casos",
    re.I,
)
_PLACE_RE = re.compile(
    r"\brua\b|\bav(\.|enida)?\b|\btravessa\b|\bcep\b|\bperto\b|\bnear\b|"
    r"\bbairro\b|\bendere[cç]o\b|\bcrimes? (near|perto)\b",
    re.I,
)
_EVENT_ID_RE = re.compile(r"\bevento(?:s)?\s+#?(\d+)\b|\bid\s*[:=]?\s*(\d+)\b", re.I)
_LEADING_PLACE_RE = re.compile(
    r"^(crimes?|mortes?|homic[ií]dios?)\s+(near|perto de|em volta de|around)\s+",
    re.I,
)

_SUBTYPE_ALIASES: dict[str, str] = {
    "feminicidio": "feminicidio",
    "feminicídio": "feminicidio",
    "femicide": "feminicidio",
    "femicidio": "feminicidio",
    "latrocinio": "latrocinio",
    "latrocínio": "latrocinio",
    "infanticidio": "infanticidio",
    "infanticídio": "infanticidio",
    "intervencao policial": "intervencao_policial",
    "intervenção policial": "intervencao_policial",
    "simples": "simples",
    "qualificado": "qualificado",
    "homicidio qualificado": "qualificado",
}


def methodology_payload() -> dict[str, Any]:
    """Shared methodology block for public stats and Ask responses."""
    return {
        "source": PUBLIC_SOURCE,
        "kind": "news_derived_archive",
        "not_official": (
            "Arquivo jornalístico derivado de notícias, não estatísticas oficiais SIM/FBSP."
        ),
        "coverage_bias": True,
        "public_window_days": PUBLIC_WINDOW_DAYS,
        "url": METHODOLOGY_URL,
        "methodology_url": METHODOLOGY_URL,
    }


def attribution() -> dict[str, str]:
    return {"source": PUBLIC_SOURCE, "methodology_url": METHODOLOGY_URL}


def normalize_state(value: str | None) -> str | None:
    """Accept UF codes or Portuguese state names (Ceará → CE)."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    key = unidecode(raw).lower()
    if key in {"rio", "rio de janeiro"}:
        # Ambiguous: prefer city context elsewhere; UF when used as a state filter.
        if "janeiro" in key or raw.upper() == "RJ":
            return "RJ"
    for uf, name in BRAZILIAN_STATE_NAMES.items():
        if unidecode(name).lower() == key:
            return uf
    return raw.upper() if len(raw) <= 3 else None


def normalize_subtype(value: str | None) -> str | None:
    if not value:
        return None
    key = unidecode(value.strip()).lower().replace("_", " ")
    if value.strip() in _HOMICIDIO_SUBTYPES:
        return value.strip()
    return _SUBTYPE_ALIASES.get(key)


def subtype_label_pt(subtype: str | None) -> str:
    if not subtype:
        return "homicídios"
    return SUBTYPE_LABELS_PT.get(("homicidio", subtype), subtype)  # type: ignore[arg-type]


def event_url(event_id: int) -> str:
    return f"{PUBLIC_SITE_URL}/eventos/{event_id}"


def map_url(*, lat: float | None = None, lng: float | None = None, state: str | None = None) -> str:
    if lat is not None and lng is not None:
        return f"{PUBLIC_SITE_URL}/?lat={lat:.5f}&lng={lng:.5f}"
    if state:
        return f"{PUBLIC_SITE_URL}/?state={quote_plus(state)}"
    return PUBLIC_SITE_URL


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _to_sorted_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
    total = sum(counts.values()) or 1
    items = [
        {"label": key, "count": value, "percent": round(value / total * 100, 1)}
        for key, value in counts.items()
    ]
    items.sort(key=lambda item: item["count"], reverse=True)
    return items


def _period_start(dt: datetime, interval: SeriesInterval) -> datetime:
    if interval == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # week — Monday
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _period_label(start: datetime, interval: SeriesInterval) -> str:
    if interval == "day":
        return start.date().isoformat()
    if interval == "month":
        return start.strftime("%Y-%m")
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def series_direction(current_count: int, previous_count: int) -> tuple[SeriesDirection, float | None]:
    """Compare equal windows. Small samples are insufficient, not a trend."""
    if current_count + previous_count < 5:
        return "insufficient", None
    if previous_count == 0:
        return ("up" if current_count >= 3 else "insufficient", None)
    change_pct = round((current_count - previous_count) / previous_count * 100, 1)
    if abs(change_pct) < 5:
        return "flat", change_pct
    if change_pct > 0:
        return "up", change_pct
    return "down", change_pct


async def query_stats_series(
    session: AsyncSession,
    *,
    state: str | None = None,
    subtype: str | None = None,
    interval: SeriesInterval = "week",
    days: int = PUBLIC_WINDOW_DAYS,
) -> dict[str, Any]:
    """Current vs previous equal window plus a bucketed series."""
    now = datetime.utcnow()
    days = max(1, min(days, PUBLIC_WINDOW_DAYS))
    current_start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)

    normalized_state = normalize_state(state)
    normalized_subtype = normalize_subtype(subtype) or (
        subtype if subtype in _HOMICIDIO_SUBTYPES else subtype
    )

    query = apply_public_incident_filter(
        select(UniqueEvent).where(
            UniqueEvent.event_date.isnot(None),
            UniqueEvent.event_date >= previous_start,
            UniqueEvent.event_date <= now,
        )
    )
    if normalized_state:
        query = query.where(UniqueEvent.state == normalized_state)
    if normalized_subtype:
        query = query.where(homicide_type_filter(normalized_subtype))

    result = await session.execute(query)
    events = result.scalars().all()

    current = [e for e in events if e.event_date and e.event_date >= current_start]
    previous = [
        e
        for e in events
        if e.event_date and previous_start <= e.event_date < current_start
    ]

    def _totals(rows: list[UniqueEvent]) -> dict[str, Any]:
        return {
            "event_count": len(rows),
            "victim_count": sum(e.victim_count or 0 for e in rows),
        }

    current_totals = _totals(current)
    previous_totals = _totals(previous)
    direction, change_pct = series_direction(
        current_totals["event_count"], previous_totals["event_count"]
    )

    buckets: dict[str, dict[str, Any]] = {}
    for event in current:
        start = _period_start(event.event_date, interval)
        label = _period_label(start, interval)
        bucket = buckets.setdefault(
            label, {"period": label, "start": start.date().isoformat(), "event_count": 0, "victim_count": 0}
        )
        bucket["event_count"] += 1
        bucket["victim_count"] += event.victim_count or 0

    series = sorted(buckets.values(), key=lambda row: row["start"])

    return {
        "state": normalized_state,
        "subtype": normalized_subtype,
        "interval": interval,
        "days": days,
        "current": {
            "start": current_start.date().isoformat(),
            "end": now.date().isoformat(),
            **current_totals,
        },
        "previous": {
            "start": previous_start.date().isoformat(),
            "end": current_start.date().isoformat(),
            **previous_totals,
        },
        "direction": direction,
        "change_pct": change_pct,
        "series": series,
        "methodology": methodology_payload(),
        **attribution(),
    }


def format_nearby_event(event: UniqueEvent, distance_km: float) -> dict[str, Any]:
    return {
        "id": event.id,
        "distance_km": round(distance_km, 2),
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "state": event.state,
        "city": event.city,
        "neighborhood": event.neighborhood,
        "homicide_type": event.homicide_type,
        "method_of_death": event.method_of_death,
        "victim_count": event.victim_count,
        "victims_summary": event.victims_summary,
        "security_force_involved": event.security_force_involved,
        "title": event.title,
        "latitude": float(event.latitude),
        "longitude": float(event.longitude),
        "location_precision": event.location_precision,
        "source_count": event.source_count,
    }


async def query_nearby(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    days: int | None = PUBLIC_WINDOW_DAYS,
    limit: int = 100,
) -> dict[str, Any]:
    """Geocoded events near a point, with type/method/precision summaries."""
    lat_delta = radius_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lng_delta = radius_km / (111.0 * cos_lat)

    query = apply_public_incident_filter(
        select(UniqueEvent).where(
            UniqueEvent.latitude.isnot(None),
            UniqueEvent.longitude.isnot(None),
            UniqueEvent.latitude >= lat - lat_delta,
            UniqueEvent.latitude <= lat + lat_delta,
            UniqueEvent.longitude >= lng - lng_delta,
            UniqueEvent.longitude <= lng + lng_delta,
        )
    )

    now = datetime.utcnow()
    cutoff = None
    prev_cutoff = None
    if days is not None:
        cutoff = now - timedelta(days=days)
        prev_cutoff = now - timedelta(days=days * 2)
        query = query.where(
            (UniqueEvent.event_date >= prev_cutoff) | (UniqueEvent.event_date.is_(None))
        )

    result = await session.execute(query)
    candidates = result.scalars().all()

    in_radius: list[tuple[float, UniqueEvent]] = []
    for event in candidates:
        try:
            elat = float(event.latitude)
            elng = float(event.longitude)
        except (TypeError, ValueError):
            continue
        distance = _haversine_km(lat, lng, elat, elng)
        if distance <= radius_km:
            in_radius.append((distance, event))

    def in_current_period(event: UniqueEvent) -> bool:
        if cutoff is None:
            return True
        return event.event_date is not None and event.event_date >= cutoff

    def in_previous_period(event: UniqueEvent) -> bool:
        if cutoff is None or prev_cutoff is None:
            return False
        return event.event_date is not None and prev_cutoff <= event.event_date < cutoff

    current = [(distance, event) for distance, event in in_radius if in_current_period(event)]
    previous_count = sum(1 for _, event in in_radius if in_previous_period(event))

    by_type: dict[str, int] = {}
    by_method: dict[str, int] = {}
    by_precision: dict[str, int] = {}
    security_involved = 0
    total_victims = 0
    for _, event in current:
        by_type[event.homicide_type or "Não classificado"] = (
            by_type.get(event.homicide_type or "Não classificado", 0) + 1
        )
        by_method[event.method_of_death or "Não especificado"] = (
            by_method.get(event.method_of_death or "Não especificado", 0) + 1
        )
        precision = event.location_precision or "desconhecida"
        by_precision[precision] = by_precision.get(precision, 0) + 1
        if event.security_force_involved:
            security_involved += 1
        if event.victim_count:
            total_victims += event.victim_count

    current_count = len(current)
    trend_pct = None
    if days is not None and previous_count > 0:
        trend_pct = round((current_count - previous_count) / previous_count * 100, 1)

    current.sort(key=lambda item: item[0])
    events = [format_nearby_event(event, distance) for distance, event in current[:limit]]

    coarse = sum(
        by_precision.get(key, 0)
        for key in ("city_center", "neighborhood_center", "centro da cidade", "centro do bairro")
    )
    precision_note = None
    if current_count and coarse / current_count >= 0.5:
        precision_note = (
            "A maioria dos eventos próximos tem precisão de centro da cidade ou do bairro; "
            "não interprete o raio como crimes nessa rua."
        )

    return {
        "center": {"lat": lat, "lng": lng},
        "radius_km": radius_km,
        "days": days,
        "summary": {
            "total": current_count,
            "total_victims": total_victims,
            "previous_period_total": previous_count if days is not None else None,
            "trend_pct": trend_pct,
            "security_force_involved": security_involved,
            "by_type": _to_sorted_counts(by_type),
            "by_method": _to_sorted_counts(by_method),
            "by_precision": _to_sorted_counts(by_precision),
            "precision_note": precision_note,
        },
        "events": events,
        **attribution(),
    }


def classify_question_heuristic(question: str) -> AskPlan:
    """Rule-based tool picker for place / trend / event lookup."""
    text = question.strip()
    event_match = _EVENT_ID_RE.search(text)
    if event_match:
        event_id = int(next(g for g in event_match.groups() if g))
        return AskPlan(intent="event_lookup", event_id=event_id, search=text)

    found_subtype = None
    for alias, slug in _SUBTYPE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", unidecode(text).lower()):
            found_subtype = slug
            break
    if re.search(r"feminic", text, re.I):
        found_subtype = "feminicidio"

    found_state = None
    lowered = unidecode(text).lower()
    for uf, name in BRAZILIAN_STATE_NAMES.items():
        name_key = unidecode(name).lower()
        if re.search(rf"\b{re.escape(name_key)}\b", lowered) or re.search(
            rf"\b{uf.lower()}\b", lowered
        ):
            # "Rio de Janeiro" as city+state in an address is handled as place below.
            found_state = uf
            break

    looks_like_place = bool(_PLACE_RE.search(text)) or bool(
        re.search(r"\d{2,5}", text) and re.search(r"rio|s[aã]o paulo|cep", text, re.I)
    )
    looks_like_trend = bool(_TREND_RE.search(text)) or (
        found_subtype and found_state and not looks_like_place
    )

    if looks_like_trend and not (looks_like_place and not _TREND_RE.search(text)):
        return AskPlan(
            intent="trend",
            state=found_state,
            subtype=found_subtype,
            days=PUBLIC_WINDOW_DAYS,
        )

    if looks_like_place or (not found_subtype and text):
        place = _LEADING_PLACE_RE.sub("", text).strip(" ?")
        return AskPlan(intent="place", place_query=place, days=PUBLIC_WINDOW_DAYS)

    if found_state or found_subtype:
        return AskPlan(intent="trend", state=found_state, subtype=found_subtype)

    return AskPlan(intent="event_lookup", search=text)


def classify_question_llm(question: str) -> AskPlan | None:
    """Optional LLM tool picker. Returns None when the key is missing or the call fails."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        return None
    try:
        import instructor

        client = instructor.from_provider(
            f"openrouter/{settings.selection_model}",
            api_key=settings.openrouter_api_key,
            mode=instructor.Mode.JSON,
        )
        return client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você escolhe ferramentas da API pública do Arquivo da Violência. "
                        "Nunca invente SQL. intent=place usa geocode+nearby; "
                        "intent=trend usa stats/series (state UF + subtype slug); "
                        "intent=event_lookup busca eventos. "
                        "Exemplos: 'Rua Umari 28, Rio' → place; "
                        "'O feminicídio está subindo no Ceará?' → trend CE feminicidio."
                    ),
                },
                {"role": "user", "content": question},
            ],
            response_model=AskPlan,
        )
    except Exception:
        return None


def classify_question(question: str) -> AskPlan:
    planned = classify_question_llm(question)
    if planned is not None:
        return planned
    return classify_question_heuristic(question)


def _precision_label_pt(value: str | None) -> str:
    labels = {
        "exact": "exata",
        "approximate": "aproximada",
        "neighborhood_center": "centro do bairro",
        "city_center": "centro da cidade",
        "desconhecida": "desconhecida",
    }
    if not value:
        return "desconhecida"
    return labels.get(value, value.replace("_", " "))


def render_place_answer(place_label: str, nearby: dict[str, Any]) -> str:
    summary = nearby["summary"]
    total = summary["total"]
    victims = summary["total_victims"]
    radius = nearby["radius_km"]
    days = nearby["days"] or PUBLIC_WINDOW_DAYS
    top_type = summary["by_type"][0]["label"] if summary["by_type"] else None
    top_precision = (
        summary["by_precision"][0]["label"] if summary["by_precision"] else None
    )
    trend = summary.get("trend_pct")
    trend_bit = ""
    if trend is not None:
        if trend > 0:
            trend_bit = f" Em relação à janela anterior, o volume noticiado subiu {trend}%."
        elif trend < 0:
            trend_bit = f" Em relação à janela anterior, o volume noticiado caiu {abs(trend)}%."
        else:
            trend_bit = " O volume noticiado ficou estável frente à janela anterior."

    type_bit = f" O tipo mais frequente é {top_type}." if top_type else ""
    precision_bit = (
        f" A precisão mais comum dos pontos é {_precision_label_pt(top_precision)} "
        "— um raio em torno da rua não implica crimes nesse logradouro."
        if top_precision
        else ""
    )
    return (
        f"Perto de {place_label} (raio de {radius:g} km, últimos {days} dias), "
        f"o arquivo registrou {total} mortes violentas noticiadas "
        f"({victims} vítimas fatais).{type_bit}{trend_bit}{precision_bit}"
    )


def render_trend_answer(plan: AskPlan, series: dict[str, Any]) -> str:
    label = subtype_label_pt(series.get("subtype") or plan.subtype)
    state = series.get("state") or plan.state or "o recorte pedido"
    state_name = BRAZILIAN_STATE_NAMES.get(state, state) if state else "o Brasil"
    current = series["current"]["event_count"]
    previous = series["previous"]["event_count"]
    victims = series["current"]["victim_count"]
    days = series["days"]
    direction = series["direction"]
    change = series.get("change_pct")

    if direction == "insufficient":
        dir_bit = (
            "Não há volume suficiente neste arquivo para afirmar se está subindo ou caindo."
        )
    elif direction == "up":
        dir_bit = (
            f"A direção no arquivo é de alta ({change}% em relação à janela anterior)."
            if change is not None
            else "A direção no arquivo é de alta."
        )
    elif direction == "down":
        dir_bit = (
            f"A direção no arquivo é de queda ({abs(change)}% em relação à janela anterior)."
            if change is not None
            else "A direção no arquivo é de queda."
        )
    else:
        dir_bit = "A direção no arquivo é estável (variação abaixo de 5%)."

    return (
        f"No {state_name}, o arquivo registrou {current} {label.lower()} noticiados "
        f"nos últimos {days} dias ({victims} vítimas), contra {previous} na janela "
        f"anterior de igual duração. {dir_bit} "
        "Isso é baseado em notícias neste arquivo, não em estatísticas oficiais."
    )


def render_lookup_answer(items: list[dict[str, Any]], search: str) -> str:
    if not items:
        return (
            f"Não encontrei eventos públicos que correspondam a “{search}” "
            "na janela do arquivo."
        )
    first = items[0]
    where = ", ".join(part for part in (first.get("city"), first.get("state")) if part)
    return (
        f"Encontrei {len(items)} evento(s) relacionados a “{search}”. "
        f"O mais recente é “{first.get('title') or 'sem título'}”"
        + (f" em {where}." if where else ".")
    )


def polish_answer_llm(question: str, draft: str, payload: dict[str, Any]) -> str:
    """Optional prose polish. Falls back to the deterministic draft."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        return draft
    try:
        import instructor

        class _Prose(BaseModel):
            answer: str

        client = instructor.from_provider(
            f"openrouter/{settings.selection_model}",
            api_key=settings.openrouter_api_key,
            mode=instructor.Mode.JSON,
        )
        result = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Reescreva em pt-BR, curto (3–6 frases), só com fatos do JSON. "
                        "Não invente números. Sempre deixe claro que o arquivo é "
                        "jornalístico, não estatística oficial. Não mencione SQL."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Pergunta: {question}\nRascunho: {draft}\nJSON: {payload}",
                },
            ],
            response_model=_Prose,
        )
        return result.answer.strip() or draft
    except Exception:
        return draft


async def lookup_events(
    session: AsyncSession,
    *,
    search: str | None = None,
    event_id: int | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    query = apply_public_incident_filter(select(UniqueEvent))
    if event_id is not None:
        query = query.where(UniqueEvent.id == event_id)
    elif search:
        like = f"%{search}%"
        query = query.where(
            UniqueEvent.title.ilike(like)
            | UniqueEvent.city.ilike(like)
            | UniqueEvent.chronological_description.ilike(like)
        )
    query = query.order_by(UniqueEvent.event_date.desc().nullslast()).limit(limit)
    result = await session.execute(query)
    rows = result.scalars().all()
    return [
        {
            "id": event.id,
            "title": event.title,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "state": event.state,
            "city": event.city,
            "homicide_type": event.homicide_type,
            "event_subtype": event.event_subtype,
            "location_precision": event.location_precision,
            "url": event_url(event.id),
        }
        for event in rows
    ]


def _citations_for_events(events: list[dict[str, Any]], extra: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    citations = [
        {
            "url": METHODOLOGY_URL,
            "label": "Metodologia do Arquivo da Violência",
        }
    ]
    for event in events[:8]:
        event_id = event.get("id")
        if event_id is None:
            continue
        citations.append(
            {
                "url": event.get("url") or event_url(int(event_id)),
                "label": event.get("title") or f"Evento {event_id}",
            }
        )
    if extra:
        citations.extend(extra)
    return citations


async def answer_question(
    session: AsyncSession,
    question: str,
    *,
    geocode_fn=None,
) -> dict[str, Any]:
    """Classify, call structured tools, return the Ask payload."""
    plan = classify_question(question)
    query_used = plan.model_dump()

    if plan.intent == "place":
        from app.services.geocoding import geocode_user_query

        geocode = geocode_fn or geocode_user_query
        geo = await geocode(plan.place_query or question)
        if not geo:
            return {
                "answer": "Não foi possível localizar esse endereço no Brasil.",
                "caveats": PLACE_CAVEATS,
                "query": query_used,
                "data": {},
                "citations": _citations_for_events([]),
                "map": None,
                "filters": None,
                **attribution(),
            }
        nearby = await query_nearby(
            session,
            lat=float(geo["latitude"]),
            lng=float(geo["longitude"]),
            radius_km=plan.radius_km,
            days=plan.days,
        )
        nearby["geocode"] = {
            "label": geo.get("label"),
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "source": geo.get("source"),
        }
        draft = render_place_answer(geo.get("label") or plan.place_query or question, nearby)
        answer = polish_answer_llm(question, draft, nearby)
        return {
            "answer": answer,
            "caveats": PLACE_CAVEATS
            + ([nearby["summary"]["precision_note"]] if nearby["summary"].get("precision_note") else []),
            "query": {**query_used, "geocode_label": geo.get("label")},
            "data": nearby,
            "citations": _citations_for_events(nearby.get("events") or []),
            "map": {
                "lat": float(geo["latitude"]),
                "lng": float(geo["longitude"]),
                "zoom": geo.get("zoom") or 13,
                "label": geo.get("label"),
            },
            "filters": None,
            **attribution(),
        }

    if plan.intent == "trend":
        series = await query_stats_series(
            session,
            state=plan.state,
            subtype=plan.subtype,
            interval="week",
            days=plan.days,
        )
        draft = render_trend_answer(plan, series)
        answer = polish_answer_llm(question, draft, series)
        filters = {
            "states": [series["state"]] if series.get("state") else [],
            "types": [series["subtype"]] if series.get("subtype") else [],
        }
        return {
            "answer": answer,
            "caveats": TREND_CAVEATS,
            "query": {**query_used, "state": series.get("state"), "subtype": series.get("subtype")},
            "data": series,
            "citations": _citations_for_events(
                [],
                extra=[{"url": map_url(state=series.get("state")), "label": "Abrir no mapa"}],
            ),
            "map": None,
            "filters": filters,
            **attribution(),
        }

    items = await lookup_events(session, search=plan.search, event_id=plan.event_id)
    draft = render_lookup_answer(items, plan.search or question)
    answer = polish_answer_llm(question, draft, {"items": items})
    first = items[0] if items else None
    return {
        "answer": answer,
        "caveats": [
            "Resultados vêm do arquivo jornalístico público, não de um cadastro oficial."
        ],
        "query": query_used,
        "data": {"items": items},
        "citations": _citations_for_events(items),
        "map": None,
        "filters": None,
        "event_id": first["id"] if first else None,
        **attribution(),
    }
