"""Reusable filters for public-facing aggregation endpoints."""

from sqlalchemy import ColumnElement, or_

from app.models.unique_event import UniqueEvent
from app.taxonomy import SUBTYPES_BY_FAMILY, parse_legacy_homicide_type

_HOMICIDIO_SUBTYPES = SUBTYPES_BY_FAMILY["homicidio"]

# Brazilian federative units (27 states + DF).
BR_UFS = frozenset(
    {
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    }
)

# Public archive: homicides only (event_family=homicidio), single incidents, BR scope.


def public_incident_criteria() -> tuple[ColumnElement, ...]:
    """SQLAlchemy criteria for public homicide archive rows."""
    return (
        UniqueEvent.event_family == "homicidio",
        UniqueEvent.content_class == "incident",
        UniqueEvent.victim_count <= 10,
        or_(UniqueEvent.state.in_(BR_UFS), UniqueEvent.state.is_(None)),
    )


def apply_public_incident_filter(statement):
    """Apply public homicide archive filters to a Select statement."""
    for criterion in public_incident_criteria():
        statement = statement.where(criterion)
    return statement


def homicide_type_filter(type_value: str) -> ColumnElement:
    """Match subtype slug, family:subtype pair, or legacy homicide_type label."""
    if type_value in _HOMICIDIO_SUBTYPES:
        return UniqueEvent.event_subtype == type_value
    if ":" in type_value:
        family, _, subtype = type_value.partition(":")
        if family and subtype:
            return (UniqueEvent.event_family == family) & (UniqueEvent.event_subtype == subtype)
    family, subtype = parse_legacy_homicide_type(type_value)
    return or_(
        UniqueEvent.homicide_type == type_value,
        (UniqueEvent.event_family == family) & (UniqueEvent.event_subtype == subtype),
    )


def homicide_types_filter(type_values: list[str]) -> ColumnElement:
    """OR of multiple homicide type filters."""
    return or_(*(homicide_type_filter(value) for value in type_values))
