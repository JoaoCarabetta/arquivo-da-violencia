"""add_event_family_subtype

Revision ID: g6h7i8j9k0l1
Revises: b2c3d4e5f6a7
Create Date: 2026-07-06 22:20:00.000000

Adds hierarchical event taxonomy columns and backfills from homicide_type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "g6h7i8j9k0l1"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_MAP: dict[str, tuple[str, str]] = {
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


def _backfill(table: str) -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, homicide_type FROM {table}")).fetchall()
    for row_id, homicide_type in rows:
        family, subtype = _LEGACY_MAP.get(
            (homicide_type or "").strip(),
            ("nao_classificado", "outro"),
        )
        conn.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET event_family = :family, event_subtype = :subtype
                WHERE id = :id
                """
            ),
            {"family": family, "subtype": subtype, "id": row_id},
        )


def upgrade() -> None:
    for table in ("raw_event", "unique_event"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "event_family",
                    sqlmodel.sql.sqltypes.AutoString(length=30),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column(
                    "event_subtype",
                    sqlmodel.sql.sqltypes.AutoString(length=30),
                    nullable=True,
                )
            )

    _backfill("raw_event")
    _backfill("unique_event")

    with op.batch_alter_table("unique_event", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_unique_event_event_family"),
            ["event_family"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_unique_event_event_subtype"),
            ["event_subtype"],
            unique=False,
        )

    with op.batch_alter_table("raw_event", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_raw_event_event_family"),
            ["event_family"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("raw_event", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_raw_event_event_family"))
        batch_op.drop_column("event_subtype")
        batch_op.drop_column("event_family")

    with op.batch_alter_table("unique_event", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_unique_event_event_subtype"))
        batch_op.drop_index(batch_op.f("ix_unique_event_event_family"))
        batch_op.drop_column("event_subtype")
        batch_op.drop_column("event_family")
