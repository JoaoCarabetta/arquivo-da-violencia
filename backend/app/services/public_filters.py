"""Reusable filters for public-facing aggregation endpoints."""

from sqlalchemy import ColumnElement, or_

from app.models.unique_event import UniqueEvent

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

# Phase A (interim, no migration): cap victim_count and exclude non-BR states by UF.
# Phase B (after AQV-28): switch to UniqueEvent.content_class == "incident".


def public_incident_criteria() -> tuple[ColumnElement, ...]:
    """SQLAlchemy criteria for plausible single-incident rows (Phase A)."""
    return (
        UniqueEvent.victim_count <= 10,
        or_(UniqueEvent.state.in_(BR_UFS), UniqueEvent.state.is_(None)),
    )


def apply_public_incident_filter(statement):
    """Apply Phase A public guardrail filters to a Select statement."""
    for criterion in public_incident_criteria():
        statement = statement.where(criterion)
    return statement
