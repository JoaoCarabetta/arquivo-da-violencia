"""add_security_force_victim

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2026-07-08 22:30:00.000000

Denormalize whether any victim is flagged as security force
(is_security_force on victims only — not perpetrators).
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


def _backfill(table: str, json_column: str) -> None:
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


def upgrade() -> None:
    for table in ("raw_event", "unique_event"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("security_force_victim", sa.Boolean(), nullable=True))
            batch_op.create_index(
                batch_op.f(f"ix_{table}_security_force_victim"),
                ["security_force_victim"],
                unique=False,
            )

    _backfill("raw_event", "extraction_data")
    _backfill("unique_event", "merged_data")


def downgrade() -> None:
    for table in ("raw_event", "unique_event"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f"ix_{table}_security_force_victim"))
            batch_op.drop_column("security_force_victim")
