"""Derived flat fields from ViolentDeathEvent for SQL columns, API, and CSV export."""

from __future__ import annotations

from typing import Any

from app.services.extraction_schemas import ViolentDeathEvent


def derive_security_force_involved(event: ViolentDeathEvent) -> bool | None:
    """Return True if any party is flagged as security force, False if explicitly not, else None."""
    flags: list[bool | None] = []

    for victim in event.victims.identifiable_victims:
        flags.append(victim.is_security_force)
    if event.victims.unidentified_groups:
        for group in event.victims.unidentified_groups:
            flags.append(group.is_security_force)

    if event.perpetrators:
        for perpetrator in event.perpetrators.identifiable_perpetrators:
            flags.append(perpetrator.is_security_force)
        if event.perpetrators.unidentified_groups:
            for group in event.perpetrators.unidentified_groups:
                flags.append(group.is_security_force)

    if any(flag is True for flag in flags):
        return True
    if flags and all(flag is False for flag in flags):
        return False
    return None


def _join_nonempty(values: list[str | None], sep: str = "; ") -> str | None:
    parts = [value.strip() for value in values if value and str(value).strip()]
    return sep.join(parts) if parts else None


def derive_public_fields(event: ViolentDeathEvent) -> dict[str, Any]:
    """Single source of truth for flat unique_event / export / API columns."""
    dynamic = event.homicide_dynamic
    cg = dynamic.criminal_group_context
    po = dynamic.police_operation_context

    criminal_group_connected = cg.connected if cg else None
    if cg and cg.activity and criminal_group_connected is None:
        criminal_group_connected = True

    politician_roles = [
        victim.political_role
        for victim in event.victims.identifiable_victims
        if victim.political_role is not None and victim.political_role.is_politician_or_candidate
    ]

    return {
        "security_force_involved": derive_security_force_involved(event),
        "criminal_group_connected": criminal_group_connected,
        "criminal_group_activity": cg.activity if cg else None,
        "criminal_group_activity_description": cg.activity_description if cg else None,
        "criminal_groups": _join_nonempty(cg.groups) if cg and cg.groups else None,
        "criminal_group_attacked": cg.group_attacked if cg else None,
        "police_operation_connected": po.connected if po else None,
        "police_operation_force": po.responsible_force if po else None,
        "police_operation_targeted_armed_groups": po.targeted_armed_groups if po else None,
        "off_duty_police_perpetrator": dynamic.off_duty_police_perpetrator,
        "off_duty_police_context": dynamic.off_duty_police_context,
        "politician_or_candidate_victim": True if politician_roles else None,
        "victim_political_status": _join_nonempty([role.status for role in politician_roles]),
        "victim_political_office": _join_nonempty([role.office for role in politician_roles]),
        "victim_political_party": _join_nonempty([role.party for role in politician_roles]),
    }


def empty_public_fields() -> dict[str, Any]:
    return {key: None for key in PUBLIC_FIELD_KEYS}


PUBLIC_FIELD_KEYS = (
    "security_force_involved",
    "criminal_group_connected",
    "criminal_group_activity",
    "criminal_group_activity_description",
    "criminal_groups",
    "criminal_group_attacked",
    "police_operation_connected",
    "police_operation_force",
    "police_operation_targeted_armed_groups",
    "off_duty_police_perpetrator",
    "off_duty_police_context",
    "politician_or_candidate_victim",
    "victim_political_status",
    "victim_political_office",
    "victim_political_party",
)


def derive_public_fields_from_data(data: dict[str, Any] | None) -> dict[str, Any]:
    """Derive flat fields from stored extraction JSON; returns nulls on parse failure."""
    if not data:
        return empty_public_fields()
    try:
        event = ViolentDeathEvent.model_validate(data)
    except Exception:
        return empty_public_fields()
    return derive_public_fields(event)
