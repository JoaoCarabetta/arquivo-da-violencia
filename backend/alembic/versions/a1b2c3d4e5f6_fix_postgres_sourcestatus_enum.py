"""fix_postgres_sourcestatus_enum

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-06 19:45:00.000000

Safety migration for Postgres: convert legacy sourcestatus enum column to VARCHAR
if a partial migration created the native enum type before status value renames.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    enum_exists = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_type WHERE typname = 'sourcestatus'"
        )
    ).scalar()
    if not enum_exists:
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE source_google_news
            ALTER COLUMN status TYPE VARCHAR(40)
            USING status::text
            """
        )
    )
    op.execute(sa.text("DROP TYPE IF EXISTS sourcestatus"))


def downgrade() -> None:
    # Irreversible: Postgres enum values no longer match the app's SourceStatus set.
    pass
