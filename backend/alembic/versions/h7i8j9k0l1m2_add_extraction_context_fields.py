"""add_extraction_context_fields

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2026-07-09 14:30:00.000000

Adds flat columns for criminal group context, police operations, off-duty police
perpetrator, political victim fields on unique_event, plus security_force_victim
on raw_event and unique_event (with backfill from extraction/merged JSON).
"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, Sequence[str], None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNIQUE_EVENT_COLUMNS = [
    ("criminal_group_connected", sa.Boolean(), True),
    ("criminal_group_activity", sa.String(length=50), False),
    ("criminal_group_activity_description", sa.Text(), False),
    ("criminal_groups", sa.String(length=512), False),
    ("criminal_group_attacked", sa.String(length=256), False),
    ("police_operation_connected", sa.Boolean(), True),
    ("police_operation_force", sa.String(length=100), False),
    ("police_operation_targeted_armed_groups", sa.Boolean(), False),
    ("off_duty_police_perpetrator", sa.Boolean(), False),
    ("off_duty_police_context", sa.String(length=50), False),
    ("politician_or_candidate_victim", sa.Boolean(), True),
    ("victim_political_status", sa.String(length=256), False),
    ("victim_political_office", sa.String(length=512), False),
    ("victim_political_party", sa.String(length=256), False),
]


def _victim_security_force_from_payload(payload: object) -> bool | None:
    if not isinstance(payload, dict):
        return None
    victims = payload.get("victims")
    if not isinstance(victims, dict):
        return None

    flags: list[bool | None] = []
    identifiable = victims.get("identifiable_victims") or []
    if isinstance(identifiable, list):
        for victim in identifiable:
            if isinstance(victim, dict):
                flags.append(victim.get("is_security_force"))

    groups = victims.get("unidentified_groups") or []
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, dict):
                flags.append(group.get("is_security_force"))

    if any(flag is True for flag in flags):
        return True
    if flags and all(flag is False for flag in flags):
        return False
    return None


def _parse_json(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _backfill_security_force_victim(table: str, json_column: str) -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, {json_column} FROM {table}")).fetchall()
    for row_id, raw_json in rows:
        flag = _victim_security_force_from_payload(_parse_json(raw_json))
        if flag is None:
            continue
        conn.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET security_force_victim = :flag
                WHERE id = :id
                """
            ),
            {"flag": flag, "id": row_id},
        )


def _join_nonempty(values: list[object], sep: str = "; ") -> str | None:
    parts = [str(value).strip() for value in values if value is not None and str(value).strip()]
    return sep.join(parts) if parts else None


def _public_fields_from_payload(payload: object) -> dict[str, object | None]:
    """Lightweight mirror of derive_public_fields for migration backfill (no app imports)."""
    empty = {
        "criminal_group_connected": None,
        "criminal_group_activity": None,
        "criminal_group_activity_description": None,
        "criminal_groups": None,
        "criminal_group_attacked": None,
        "police_operation_connected": None,
        "police_operation_force": None,
        "police_operation_targeted_armed_groups": None,
        "off_duty_police_perpetrator": None,
        "off_duty_police_context": None,
        "politician_or_candidate_victim": None,
        "victim_political_status": None,
        "victim_political_office": None,
        "victim_political_party": None,
    }
    if not isinstance(payload, dict):
        return empty

    dynamic = payload.get("homicide_dynamic")
    if not isinstance(dynamic, dict):
        dynamic = {}
    cg = dynamic.get("criminal_group_context")
    if not isinstance(cg, dict):
        cg = {}
    po = dynamic.get("police_operation_context")
    if not isinstance(po, dict):
        po = {}

    connected = cg.get("connected")
    activity = cg.get("activity")
    if activity and connected is None:
        connected = True

    victims = payload.get("victims")
    politician_roles: list[dict] = []
    if isinstance(victims, dict):
        identifiable = victims.get("identifiable_victims") or []
        if isinstance(identifiable, list):
            for victim in identifiable:
                if not isinstance(victim, dict):
                    continue
                role = victim.get("political_role")
                if isinstance(role, dict) and role.get("is_politician_or_candidate") is True:
                    politician_roles.append(role)

    groups = cg.get("groups")
    return {
        "criminal_group_connected": connected,
        "criminal_group_activity": activity,
        "criminal_group_activity_description": cg.get("activity_description"),
        "criminal_groups": _join_nonempty(groups) if isinstance(groups, list) else None,
        "criminal_group_attacked": cg.get("group_attacked"),
        "police_operation_connected": po.get("connected"),
        "police_operation_force": po.get("responsible_force"),
        "police_operation_targeted_armed_groups": po.get("targeted_armed_groups"),
        "off_duty_police_perpetrator": dynamic.get("off_duty_police_perpetrator"),
        "off_duty_police_context": dynamic.get("off_duty_police_context"),
        "politician_or_candidate_victim": True if politician_roles else None,
        "victim_political_status": _join_nonempty([role.get("status") for role in politician_roles]),
        "victim_political_office": _join_nonempty([role.get("office") for role in politician_roles]),
        "victim_political_party": _join_nonempty([role.get("party") for role in politician_roles]),
    }


def _backfill_unique_event_context_fields() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, merged_data FROM unique_event")).fetchall()
    column_names = [name for name, _, _ in _UNIQUE_EVENT_COLUMNS]
    for row_id, raw_json in rows:
        fields = _public_fields_from_payload(_parse_json(raw_json))
        values = {name: fields.get(name) for name in column_names}
        if all(value is None for value in values.values()):
            continue
        assignments = ", ".join(f"{name} = :{name}" for name in column_names)
        values["id"] = row_id
        conn.execute(
            sa.text(f"UPDATE unique_event SET {assignments} WHERE id = :id"),
            values,
        )


def upgrade() -> None:
    with op.batch_alter_table("unique_event", schema=None) as batch_op:
        for name, col_type, indexed in _UNIQUE_EVENT_COLUMNS:
            batch_op.add_column(sa.Column(name, col_type, nullable=True))
            if indexed:
                batch_op.create_index(batch_op.f(f"ix_unique_event_{name}"), [name], unique=False)

    for table in ("raw_event", "unique_event"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("security_force_victim", sa.Boolean(), nullable=True))
            batch_op.create_index(
                batch_op.f(f"ix_{table}_security_force_victim"),
                ["security_force_victim"],
                unique=False,
            )

    _backfill_security_force_victim("raw_event", "extraction_data")
    _backfill_security_force_victim("unique_event", "merged_data")
    _backfill_unique_event_context_fields()


def downgrade() -> None:
    for table in ("raw_event", "unique_event"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f"ix_{table}_security_force_victim"))
            batch_op.drop_column("security_force_victim")

    with op.batch_alter_table("unique_event", schema=None) as batch_op:
        for name, _, indexed in reversed(_UNIQUE_EVENT_COLUMNS):
            if indexed:
                batch_op.drop_index(batch_op.f(f"ix_unique_event_{name}"))
            batch_op.drop_column(name)
