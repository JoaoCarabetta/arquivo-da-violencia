"""Deterministic post-LLM fixes for extraction (method, subtype, content_class, date)."""

from __future__ import annotations

import re
from datetime import datetime
from unidecode import unidecode

from app.services.extraction_schemas import ViolentDeathEvent
from app.taxonomy import MethodOfDeath

_METHOD_RULES: list[tuple[tuple[str, ...], MethodOfDeath]] = [
    (
        (
            "disparo",
            "tiros",
            "tiro ",
            "baleado",
            "baleada",
            "baleados",
            "execute",
            "executado",
            "executada",
            "queima-roupa",
            "queima roupa",
            "revolver",
            "revólver",
            "pistola",
            "fuzil",
            "calibre",
            "marcas de tiros",
        ),
        "Arma de fogo",
    ),
    (
        ("facada", "facadas", "faca", "punhal", "facao", "facão", "golpes de faca"),
        "Arma branca",
    ),
    (("estrangul", "enforcad", "enforcam", "asfixi"), "Estrangulamento"),
    (("atropel",), "Atropelamento"),
    (("envenen", "intoxic"), "Envenenamento"),
    (("espanc", "socos", "pauladas", "sinais de espancamento"), "Espancamento"),
    (
        (
            "objeto contundente",
            "contundente",
            "traumatismo craniano",
            "ferimento profundo na cabeca",
            "ferimento profundo na cabeça",
        ),
        "Objeto contundente",
    ),
]

_QUALIFICADO_MARKERS = (
    "queima-roupa",
    "queima roupa",
    "dezenas de tiros",
    "multiplos disparos a queima-roupa",
    "múltiplos disparos à queima-roupa",
    "multiplos disparos a queima roupa",
    "múltiplos disparos à queima roupa",
    "chacina",
    "maos e os pes amarrados",
    "mãos e os pés amarrados",
    "maos e pes amarrados",
    "pes amarrados",
    "tortura",
    "emboscada",
)

_UNSPECIFIED_METHOD_MARKERS = (
    "nao conseguiu determinar",
    "não conseguiu determinar",
    "nao foi possivel determinar",
    "não foi possível determinar",
    "objeto usado no crime",
    "metodo nao",
    "método não",
    "causa nao divulgada",
    "causa não divulgada",
    "causa da morte nao",
    "causa da morte não",
    "sem informacoes sobre",
    "sem informações sobre",
)

_WEEKDAY_PAREN_DAY = re.compile(
    r"(?:domingo|segunda(?:-feira)?|terca(?:-feira)?|terça(?:-feira)?|"
    r"quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|sabado|sábado)\s*\((\d{1,2})\)",
    re.IGNORECASE,
)

_RELATIVE_THIS_WEEKDAY = re.compile(
    r"(?:neste|nesta|deste|desta)\s+"
    r"(domingo|segunda(?:-feira)?|terca(?:-feira)?|terça(?:-feira)?|"
    r"quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|sabado|sábado)\b",
    re.IGNORECASE,
)

_WEEKDAY_TO_NUM = {
    "domingo": 6,
    "segunda": 0,
    "segunda-feira": 0,
    "terca": 1,
    "terça": 1,
    "terca-feira": 1,
    "terça-feira": 1,
    "quarta": 2,
    "quarta-feira": 2,
    "quinta": 3,
    "quinta-feira": 3,
    "sexta": 4,
    "sexta-feira": 4,
    "sabado": 5,
    "sábado": 5,
}

_COUNT_WORDS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
}

_DEAD_AND_WOUNDED = re.compile(
    r"\b(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+"
    r"(?:pessoas?\s+)?mort(?:a|o|as|os|es)?\s+e\s+"
    r"(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+ferid",
    re.IGNORECASE,
)

_HEADLINE_DEAD_WOUNDED = re.compile(
    r"deixa\s+(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+"
    r"mortos?\s+e\s+"
    r"(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+ferid",
    re.IGNORECASE,
)

_CG_MS_HINTS = ("campo grande news", "campograndenews")

_SCANT_CLASSIFICATION_MARKERS = (
    "nao ha detalhes sobre a identidade",
    "não há detalhes sobre a identidade",
    "nenhuma outra informacao foi divulgada",
    "nenhuma outra informação foi divulgada",
)

_HYPOTHESIS_MARKERS = (
    "hipotese",
    "hipótese",
    "linha de investigacao",
    "linha de investigação",
    "principal hipotese",
    "principal hipótese",
)

_PATROL_SHOOTOUT_MARKERS = (
    "recebidas a tiros",
    "reagiu atirando",
    "grupo de criminosos",
    "confronto entre policiais",
    "troca de tiros com",
    "patrulhamento",
    "abordagem",
    "abordar um veiculo",
    "abordar um veículo",
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return unidecode(text.lower())


def _source_text(content: str, metadata: dict | None) -> str:
    """Original article text only — avoid LLM paraphrases in subtype rules."""
    parts = [content, (metadata or {}).get("headline") or ""]
    return _norm(" ".join(parts))


def _combined_text(
    event: ViolentDeathEvent,
    content: str,
    metadata: dict | None,
) -> str:
    parts = [
        content,
        (metadata or {}).get("headline") or "",
        event.homicide_dynamic.title or "",
        event.homicide_dynamic.chronological_description or "",
    ]
    return _norm(" ".join(parts))


def infer_method_from_text(text: str) -> MethodOfDeath | None:
    normalized = _norm(text)
    for keywords, method in _METHOD_RULES:
        if any(kw in normalized for kw in keywords):
            return method
    return None


def should_use_unspecified_method(text: str) -> bool:
    normalized = _norm(text)
    if infer_method_from_text(normalized) == "Arma de fogo" and any(
        marker in normalized
        for marker in (
            "marca de tiro",
            "marcas de tiro",
            "disparo",
            "balead",
            " tiro",
            "tiros",
        )
    ):
        return False
    if any(marker in normalized for marker in _UNSPECIFIED_METHOD_MARKERS):
        return True
    if "corpo" in normalized and "encontrado" in normalized and not infer_method_from_text(
        normalized
    ):
        if any(
            phrase in normalized
            for phrase in ("causa", "metodo", "método", "hipotese", "hipótese")
        ):
            return True
    return False


def is_patrol_shootout_not_intervention(text: str) -> bool:
    normalized = _norm(text)
    if not any(
        marker in normalized
        for marker in ("policia", "pm ", "rota", "policiais militares")
    ):
        return False
    return any(marker in normalized for marker in _PATROL_SHOOTOUT_MARKERS)


def _is_hypothesis_executado(normalized: str) -> bool:
    """Ignore 'executado' used in investigative hypothesis, not as crime description."""
    if "executado em outro local" in normalized or "morto em outro local" in normalized:
        return True
    if "executado" not in normalized:
        return False
    for marker in _HYPOTHESIS_MARKERS:
        idx = normalized.find(marker)
        if idx >= 0 and "executado" in normalized[idx : idx + 140]:
            return True
    return False


def should_be_qualificado(text: str) -> bool:
    normalized = _norm(text)
    if _is_hypothesis_executado(normalized):
        return False
    if any(marker in normalized for marker in _QUALIFICADO_MARKERS):
        return True
    if "executado" in normalized and infer_method_from_text(normalized) == "Arma de fogo":
        return True
    if re.search(r"\bexecu(?:cao|ção)\b", normalized) and "tiro" in normalized:
        return True
    return False


def _parse_published_at(metadata: dict | None) -> datetime | None:
    if not metadata:
        return None
    published_at = metadata.get("published_at")
    if not published_at:
        return None
    if isinstance(published_at, datetime):
        return published_at
    if isinstance(published_at, str):
        try:
            return datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def fix_weekday_paren_day(
    content: str,
    metadata: dict | None,
    current_date: str | None,
) -> str | None:
    """When text says 'domingo (10)', prefer day-of-month in parentheses over weekday."""
    match = _WEEKDAY_PAREN_DAY.search(content)
    if not match:
        return None
    day = int(match.group(1))
    if day < 1 or day > 31:
        return None
    published = _parse_published_at(metadata)
    if not published:
        return None
    try:
        candidate = published.replace(day=day)
    except ValueError:
        return None
    fixed = candidate.strftime("%Y-%m-%d")
    if fixed == current_date:
        return None
    return fixed


def fix_same_day_relative_weekday(
    content: str,
    metadata: dict | None,
    current_date: str | None,
) -> str | None:
    """Resolve 'deste sábado' / 'neste domingo' when publication is that weekday."""
    match = _RELATIVE_THIS_WEEKDAY.search(content)
    if not match:
        return None
    weekday_key = _norm(match.group(1))
    expected_dow = _WEEKDAY_TO_NUM.get(weekday_key)
    if expected_dow is None:
        return None
    published = _parse_published_at(metadata)
    if not published:
        return None
    if published.weekday() != expected_dow:
        return None
    fixed = published.strftime("%Y-%m-%d")
    if fixed == current_date:
        return None
    return fixed


def infer_date_from_source(
    content: str,
    metadata: dict | None,
    current_date: str | None,
) -> str | None:
    """Apply deterministic date fixes from article text + publication metadata."""
    return fix_weekday_paren_day(content, metadata, current_date) or fix_same_day_relative_weekday(
        content, metadata, current_date
    )


def normalize_date_string(date: str | None) -> str | None:
    """Coerce ISO datetimes to YYYY-MM-DD for eval and storage consistency."""
    if not date:
        return date
    if "T" in date:
        return date.split("T", 1)[0]
    return date


def _parse_count_token(token: str) -> int | None:
    normalized = _norm(token.strip())
    if normalized.isdigit():
        value = int(normalized)
        return value if 1 <= value <= 20 else None
    return _COUNT_WORDS.get(normalized)


def infer_fatal_victim_count(source: str) -> int | None:
    """Extract dead-only count from 'X mortos e Y feridos' phrasing."""
    for pattern in (_DEAD_AND_WOUNDED, _HEADLINE_DEAD_WOUNDED):
        match = pattern.search(source)
        if match:
            count = _parse_count_token(match.group(1))
            if count:
                return count
    return None


def infer_state_from_metadata(city: str | None, metadata: dict | None) -> str | None:
    """Disambiguate Campo Grande (MS) using publisher/url when city alone is ambiguous."""
    if _norm(city) != "campo grande" or not metadata:
        return None
    publisher = _norm(str(metadata.get("publisher") or ""))
    url = _norm(str(metadata.get("url") or ""))
    if any(hint in publisher or hint in url for hint in _CG_MS_HINTS):
        return "MS"
    return None


def is_insufficient_classification_case(source: str) -> bool:
    """Articles with only 'body found' and no confirmed violent cause."""
    if "corpo" not in source:
        return False
    if infer_method_from_text(source):
        return False
    if any(
        marker in source
        for marker in (
            "assassin",
            "homicidio",
            "executad",
            "balead",
            " tiros",
            "disparo",
            "facad",
            "espanc",
        )
    ):
        return False
    return any(marker in source for marker in _SCANT_CLASSIFICATION_MARKERS)


def apply_extraction_heuristics(
    event: ViolentDeathEvent,
    content: str,
    metadata: dict | None = None,
) -> ViolentDeathEvent:
    """Apply deterministic corrections aligned with prod taxonomy and eval labels."""
    source = _source_text(content, metadata)
    updates: dict = {}

    if is_insufficient_classification_case(source):
        updates["event_family"] = "nao_classificado"
        updates["event_subtype"] = "outro"

    if event.event_family == "acidente_fatal":
        updates["content_class"] = "accident_disaster"

    subtype = event.event_subtype
    family = updates.get("event_family", event.event_family)
    if family == "homicidio":
        if subtype == "intervencao_policial" and is_patrol_shootout_not_intervention(source):
            subtype = "simples"
        elif subtype == "simples" and should_be_qualificado(source):
            subtype = "qualificado"
        elif subtype == "qualificado" and not should_be_qualificado(source):
            subtype = "simples"
        if subtype != event.event_subtype:
            updates["event_subtype"] = subtype

    method = event.homicide_dynamic.method
    if should_use_unspecified_method(source):
        method = "Não especificado"
    elif method == "Outro":
        method = "Não especificado"
    elif method is None:
        inferred = infer_method_from_text(source)
        if inferred:
            method = inferred
    elif method == "Objeto contundente" and "espanc" in source:
        method = "Espancamento"

    if method != event.homicide_dynamic.method:
        hd = event.homicide_dynamic.model_copy(update={"method": method})
        updates["homicide_dynamic"] = hd

    fixed_date = infer_date_from_source(content, metadata, event.date_time.date)
    normalized_date = normalize_date_string(fixed_date or event.date_time.date)
    if normalized_date != event.date_time.date:
        dt = event.date_time.model_copy(update={"date": normalized_date})
        updates["date_time"] = dt

    fatal_count = infer_fatal_victim_count(source)
    if fatal_count and event.victims.number_of_victims != fatal_count:
        victims = event.victims.model_copy(update={"number_of_victims": fatal_count})
        updates["victims"] = victims

    inferred_state = infer_state_from_metadata(event.location_info.city, metadata)
    if inferred_state and event.location_info.state != inferred_state:
        location = event.location_info.model_copy(update={"state": inferred_state})
        updates["location_info"] = location

    if not updates:
        return event
    return event.model_copy(update=updates)
