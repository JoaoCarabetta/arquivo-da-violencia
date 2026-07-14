"""Canonical event taxonomy: event_family (macro) + event_subtype (leaf).

The public archive is homicide-focused: only ``event_family == homicidio`` rows
with ``content_class == incident`` appear on the public map and stats.
"""

from __future__ import annotations

from typing import Literal

ContentClass = Literal[
    "incident",
    "aggregate_statistics",
    "non_incident",
    "accident_disaster",
    "foreign",
]

EventFamily = Literal["homicidio", "tentativa", "acidente_fatal", "nao_classificado"]

EventSubtype = Literal[
    "simples",
    "qualificado",
    "feminicidio",
    "latrocinio",
    "infanticidio",
    "intervencao_policial",
    "morte_transito_doloso",
    "culposo",
    "transito_culposo",
    "outro",
]

MethodOfDeath = Literal[
    "Arma de fogo",
    "Arma branca",
    "Estrangulamento",
    "Asfixia",
    "Espancamento",
    "Atropelamento",
    "Envenenamento",
    "Objeto contundente",
    "Incêndio",
    "Queda",
    "Outro",
    "Não especificado",
]

SUBTYPES_BY_FAMILY: dict[EventFamily, frozenset[EventSubtype]] = {
    "homicidio": frozenset(
        {
            "simples",
            "qualificado",
            "feminicidio",
            "latrocinio",
            "infanticidio",
            "intervencao_policial",
            "morte_transito_doloso",
        }
    ),
    "tentativa": frozenset({"simples", "feminicidio", "latrocinio"}),
    "acidente_fatal": frozenset({"culposo", "transito_culposo"}),
    "nao_classificado": frozenset({"outro"}),
}

PUBLIC_FAMILIES: frozenset[EventFamily] = frozenset({"homicidio"})

# Display labels (PT) keyed by (family, subtype).
SUBTYPE_LABELS_PT: dict[tuple[EventFamily, EventSubtype], str] = {
    ("homicidio", "simples"): "Homicídio simples",
    ("homicidio", "qualificado"): "Homicídio qualificado",
    ("homicidio", "feminicidio"): "Feminicídio",
    ("homicidio", "latrocinio"): "Latrocínio",
    ("homicidio", "infanticidio"): "Infanticídio",
    ("homicidio", "intervencao_policial"): "Intervenção policial",
    ("homicidio", "morte_transito_doloso"): "Morte dolosa no trânsito",
    ("tentativa", "simples"): "Tentativa de homicídio",
    ("tentativa", "feminicidio"): "Tentativa de feminicídio",
    ("tentativa", "latrocinio"): "Tentativa de latrocínio",
    ("acidente_fatal", "culposo"): "Homicídio culposo",
    ("acidente_fatal", "transito_culposo"): "Acidente de trânsito fatal",
    ("nao_classificado", "outro"): "Não especificado",
}

FAMILY_LABELS_PT: dict[EventFamily, str] = {
    "homicidio": "Homicídio",
    "tentativa": "Tentativa",
    "acidente_fatal": "Acidente fatal",
    "nao_classificado": "Não classificado",
}

# Legacy flat homicide_type strings (prod + extraction history) → (family, subtype).
LEGACY_HOMICIDE_TYPE_MAP: dict[str, tuple[EventFamily, EventSubtype]] = {
    "Homicídio": ("homicidio", "simples"),
    "Homicídio Qualificado": ("homicidio", "qualificado"),
    "Feminicídio": ("homicidio", "feminicidio"),
    "Latrocínio": ("homicidio", "latrocinio"),
    "Infanticídio": ("homicidio", "infanticidio"),
    "Intervenção policial": ("homicidio", "intervencao_policial"),
    "Morte no trânsito": ("homicidio", "morte_transito_doloso"),
    "Tentativa de Homicídio": ("tentativa", "simples"),
    "Homicídio Culposo": ("acidente_fatal", "culposo"),
    "Outro": ("nao_classificado", "outro"),
}

# Reverse map for backward-compatible homicide_type column.
_LABEL_TO_LEGACY: dict[tuple[EventFamily, EventSubtype], str] = {
    v: k for k, v in LEGACY_HOMICIDE_TYPE_MAP.items()
}


class TaxonomyValidationError(ValueError):
    """Raised when event_family and event_subtype are inconsistent."""


def validate_family_subtype(family: EventFamily, subtype: EventSubtype) -> None:
    """Raise if subtype is not valid for the given family."""
    allowed = SUBTYPES_BY_FAMILY.get(family)
    if allowed is None or subtype not in allowed:
        raise TaxonomyValidationError(
            f"event_subtype {subtype!r} is not valid for event_family {family!r}"
        )


def format_event_label(family: EventFamily, subtype: EventSubtype) -> str:
    """Human-readable PT label for a (family, subtype) pair."""
    validate_family_subtype(family, subtype)
    return SUBTYPE_LABELS_PT[(family, subtype)]


def format_legacy_homicide_type(family: EventFamily, subtype: EventSubtype) -> str:
    """Backward-compatible flat homicide_type string for API/CSV export."""
    validate_family_subtype(family, subtype)
    key = (family, subtype)
    if key in _LABEL_TO_LEGACY:
        return _LABEL_TO_LEGACY[key]
    return format_event_label(family, subtype)


def parse_legacy_homicide_type(flat: str | None) -> tuple[EventFamily, EventSubtype]:
    """Map legacy flat homicide_type to (event_family, event_subtype)."""
    if not flat or not flat.strip():
        return ("nao_classificado", "outro")
    normalized = flat.strip()
    if normalized in LEGACY_HOMICIDE_TYPE_MAP:
        return LEGACY_HOMICIDE_TYPE_MAP[normalized]
    lower = normalized.lower()
    if "tentativa" in lower and "feminic" in lower:
        return ("tentativa", "feminicidio")
    if "tentativa" in lower and "latroc" in lower:
        return ("tentativa", "latrocinio")
    if "tentativa" in lower:
        return ("tentativa", "simples")
    if "policial vitimado" in lower or "homicídio de policial" in lower or "homicidio de policial" in lower:
        return ("homicidio", "simples")
    if "culposo" in lower or "acidente" in lower and "trânsito" in lower:
        return ("acidente_fatal", "transito_culposo" if "trânsito" in lower or "transito" in lower else "culposo")
    return ("nao_classificado", "outro")


def is_public_incident(
    family: EventFamily | str | None,
    subtype: EventSubtype | str | None,
    *,
    content_class: ContentClass | str = "incident",
    victim_count: int | None = None,
) -> bool:
    """Whether a row belongs on the public homicide archive (map/stats/export)."""
    if family != "homicidio":
        return False
    if content_class != "incident":
        return False
    if victim_count is not None and victim_count > 10:
        return False
    if subtype is not None:
        try:
            validate_family_subtype("homicidio", subtype)  # type: ignore[arg-type]
        except TaxonomyValidationError:
            return False
    return True


def default_subtype_for_family(family: EventFamily) -> EventSubtype:
    """Default leaf subtype when only the family is known."""
    defaults: dict[EventFamily, EventSubtype] = {
        "homicidio": "simples",
        "tentativa": "simples",
        "acidente_fatal": "culposo",
        "nao_classificado": "outro",
    }
    return defaults[family]
