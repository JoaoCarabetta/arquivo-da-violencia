"""Reusable filters for public-facing aggregation endpoints."""

from sqlalchemy import ColumnElement, or_

from app.models.unique_event import UniqueEvent
from app.taxonomy import SUBTYPES_BY_FAMILY, parse_legacy_homicide_type
from app.geography import BRAZILIAN_STATES, CHILEAN_REGIONS

_HOMICIDIO_SUBTYPES = SUBTYPES_BY_FAMILY["homicidio"]

# Brazilian federative units (27 states + DF).
BR_UFS = frozenset(BRAZILIAN_STATES)

# Chilean regions (regiones)
CL_REGIONS = frozenset(CHILEAN_REGIONS)

# Public archive: homicides only (event_family=homicidio), single incidents.


def public_incident_criteria(country: str | None = None) -> tuple[ColumnElement, ...]:
    """SQLAlchemy criteria for public homicide archive rows.
    
    Args:
        country: Optional country filter for state allowlist.
                 - When "BR" or "Brasil": only BR UFs or null
                 - When "CL": no state filtering (all Chilean regions allowed)
                 - When None (default): allow both BR UFs and CL regions (for unfiltered queries)
    """
    base_criteria = (
        UniqueEvent.event_family == "homicidio",
        UniqueEvent.content_class == "incident",
        UniqueEvent.victim_count <= 10,
    )
    
    # Apply country-specific state filtering
    if country is not None and country.upper() == "CL":
        # CL: no state filtering (allow all Chilean regions)
        return base_criteria
    elif country is not None and country.upper() in ("BR", "BRASIL"):
        # BR/Brasil explicit: only allow valid Brazilian UFs or null
        return base_criteria + (
            or_(UniqueEvent.state.in_(BR_UFS), UniqueEvent.state.is_(None)),
        )
    else:
        # No country filter (None): allow both BR UFs and CL regions or null (default for mixed queries)
        valid_states = BR_UFS.union(CL_REGIONS)
        return base_criteria + (
            or_(UniqueEvent.state.in_(valid_states), UniqueEvent.state.is_(None)),
        )


def apply_public_incident_filter(statement, country: str | None = None):
    """Apply public homicide archive filters to a Select statement.
    
    Args:
        statement: SQLAlchemy Select statement
        country: Optional country code for country-specific filtering
    """
    for criterion in public_incident_criteria(country):
        statement = statement.where(criterion)
    return statement


def homicide_type_filter(type_value: str) -> ColumnElement:
    """Match subtype slug, family:subtype pair, legacy label, or security_force_victim."""
    lower = type_value.lower()
    if type_value == "security_force_victim" or "policial vitimado" in lower or "homicídio de policial" in lower or "homicidio de policial" in lower:
        return UniqueEvent.security_force_victim.is_(True)
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
