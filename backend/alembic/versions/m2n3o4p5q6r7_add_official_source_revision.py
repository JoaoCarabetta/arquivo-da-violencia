"""add_official_source_revision

Revision ID: m2n3o4p5q6r7
Revises: l1m2n3o4p5q6
Create Date: 2026-09-15 22:00:00.000000

Add source_id and revision columns to official_violence_count for multi-source
official data (issue #238). Backfill existing rows as validador + consolidado.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "m2n3o4p5q6r7"
down_revision: Union[str, Sequence[str], None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def _unique_constraint_exists(bind, table_name: str, column_names: set[str]) -> bool:
    inspector = inspect(bind)
    constraints = inspector.get_unique_constraints(table_name)
    return any(set(c["column_names"]) == column_names for c in constraints)


def upgrade() -> None:
    """Add source_id/revision and expand unique key to five columns."""
    bind = op.get_bind()

    if not _column_exists(bind, "official_violence_count", "source_id"):
        op.add_column(
            "official_violence_count",
            sa.Column(
                "source_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="validador",
            ),
        )
        op.create_index(
            op.f("ix_official_violence_count_source_id"),
            "official_violence_count",
            ["source_id"],
            unique=False,
        )

    if not _column_exists(bind, "official_violence_count", "revision"):
        op.add_column(
            "official_violence_count",
            sa.Column(
                "revision",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="consolidado",
            ),
        )
        op.create_index(
            op.f("ix_official_violence_count_revision"),
            "official_violence_count",
            ["revision"],
            unique=False,
        )

    # Backfill any nulls (defensive; server_default should cover existing rows)
    op.execute(
        "UPDATE official_violence_count SET source_id = 'validador' "
        "WHERE source_id IS NULL OR source_id = ''"
    )
    op.execute(
        "UPDATE official_violence_count SET revision = 'consolidado' "
        "WHERE revision IS NULL OR revision = ''"
    )

    # Replace 3-column unique key with 5-column key
    inspector = inspect(bind)
    constraints = inspector.get_unique_constraints("official_violence_count")
    old_key_names = [
        c["name"]
        for c in constraints
        if set(c["column_names"]) == {"code_muni", "year_month", "indicator"}
    ]
    for name in old_key_names:
        op.drop_constraint(name, "official_violence_count", type_="unique")

    if not _unique_constraint_exists(
        bind,
        "official_violence_count",
        {"code_muni", "year_month", "indicator", "source_id", "revision"},
    ):
        op.create_unique_constraint(
            "uq_official_violence_key",
            "official_violence_count",
            ["code_muni", "year_month", "indicator", "source_id", "revision"],
        )


def downgrade() -> None:
    """Revert to 3-column unique key and drop source_id/revision."""
    bind = op.get_bind()

    inspector = inspect(bind)
    constraints = inspector.get_unique_constraints("official_violence_count")
    new_key_names = [
        c["name"]
        for c in constraints
        if set(c["column_names"])
        == {"code_muni", "year_month", "indicator", "source_id", "revision"}
    ]
    for name in new_key_names:
        op.drop_constraint(name, "official_violence_count", type_="unique")

    if not _unique_constraint_exists(
        bind,
        "official_violence_count",
        {"code_muni", "year_month", "indicator"},
    ):
        op.create_unique_constraint(
            "uq_official_violence_key",
            "official_violence_count",
            ["code_muni", "year_month", "indicator"],
        )

    if _column_exists(bind, "official_violence_count", "revision"):
        op.drop_index(
            op.f("ix_official_violence_count_revision"),
            table_name="official_violence_count",
        )
        op.drop_column("official_violence_count", "revision")

    if _column_exists(bind, "official_violence_count", "source_id"):
        op.drop_index(
            op.f("ix_official_violence_count_source_id"),
            table_name="official_violence_count",
        )
        op.drop_column("official_violence_count", "source_id")
