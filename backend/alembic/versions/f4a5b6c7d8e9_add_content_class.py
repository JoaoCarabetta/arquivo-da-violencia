"""add_content_class

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-03 14:17:00.000000

This migration:
1. Adds content_class to raw_event
2. Adds content_class to unique_event (indexed for public filter Phase B)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add content_class columns with default 'incident'."""

    with op.batch_alter_table('raw_event', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'content_class',
                sqlmodel.sql.sqltypes.AutoString(length=30),
                nullable=False,
                server_default='incident',
            )
        )

    with op.batch_alter_table('unique_event', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'content_class',
                sqlmodel.sql.sqltypes.AutoString(length=30),
                nullable=False,
                server_default='incident',
            )
        )
        batch_op.create_index(
            batch_op.f('ix_unique_event_content_class'),
            ['content_class'],
            unique=False,
        )


def downgrade() -> None:
    """Remove content_class columns."""

    with op.batch_alter_table('unique_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_unique_event_content_class'))
        batch_op.drop_column('content_class')

    with op.batch_alter_table('raw_event', schema=None) as batch_op:
        batch_op.drop_column('content_class')
