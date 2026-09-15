"""fix_postgres_official_enum_varchar

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2026-09-15 23:00:00.000000

Safety migration for Postgres: convert legacy officialsourceid/officialrevision
enum columns to lowercase VARCHAR if SQLModel create_all or ops patches created
native enum types with uppercase labels (issue #252).

When enum types exist, order is critical (issue #254):
  1. DROP DEFAULT on source_id / revision (defaults depend on enum types)
  2. ALTER COLUMN … TYPE VARCHAR USING lower(…::text)
  3. SET DEFAULT to lowercase strings ('validador', 'consolidado')
  4. DROP TYPE officialsourceid / officialrevision
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


def _convert_column_to_varchar(
    bind, column_name: str, length: int, lowercase_default: str
) -> None:
    # 1. DROP DEFAULT — column defaults reference enum types and block DROP TYPE.
    op.execute(
        sa.text(
            f"ALTER TABLE official_violence_count "
            f"ALTER COLUMN {column_name} DROP DEFAULT"
        )
    )
    # 2. Convert enum values to lowercase VARCHAR.
    op.execute(
        sa.text(
            f"""
            ALTER TABLE official_violence_count
            ALTER COLUMN {column_name} TYPE VARCHAR({length})
            USING lower({column_name}::text)
            """
        )
    )
    # 3. Restore lowercase string default (matches m2n3o4p5q6r7 server_default).
    op.execute(
        sa.text(
            f"ALTER TABLE official_violence_count "
            f"ALTER COLUMN {column_name} SET DEFAULT '{lowercase_default}'"
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
        _convert_column_to_varchar(bind, "source_id", 20, "validador")
        # 4. DROP TYPE — safe once defaults no longer reference the enum.
        op.execute(sa.text("DROP TYPE IF EXISTS officialsourceid"))

    if revision_enum:
        _convert_column_to_varchar(bind, "revision", 20, "consolidado")
        op.execute(sa.text("DROP TYPE IF EXISTS officialrevision"))


def downgrade() -> None:
    # Irreversible: lowercase VARCHAR values no longer match native enum labels.
    pass
