"""fix_postgres_official_enum_varchar

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2026-09-15 23:00:00.000000

Safety migration for Postgres: convert legacy officialsourceid/officialrevision
enum columns to VARCHAR if SQLModel create_all created native enum types before
sa_column overrides (issue #252).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n3o4p5q6r7s8"
down_revision: Union[str, Sequence[str], None] = "m2n3o4p5q6r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum_type_exists(bind, type_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
            {"name": type_name},
        ).scalar()
    )


def _convert_column_to_varchar(bind, column_name: str, length: int) -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE official_violence_count
            ALTER COLUMN {column_name} TYPE VARCHAR({length})
            USING {column_name}::text
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    source_enum = _enum_type_exists(bind, "officialsourceid")
    revision_enum = _enum_type_exists(bind, "officialrevision")
    if not source_enum and not revision_enum:
        return

    if source_enum:
        _convert_column_to_varchar(bind, "source_id", 20)
        op.execute(sa.text("DROP TYPE IF EXISTS officialsourceid"))

    if revision_enum:
        _convert_column_to_varchar(bind, "revision", 20)
        op.execute(sa.text("DROP TYPE IF EXISTS officialrevision"))


def downgrade() -> None:
    # Irreversible: lowercase VARCHAR values no longer match native enum labels.
    pass
