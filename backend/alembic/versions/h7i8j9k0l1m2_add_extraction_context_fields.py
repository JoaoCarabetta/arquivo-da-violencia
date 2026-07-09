"""add_extraction_context_fields

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2026-07-09 14:30:00.000000

Adds flat columns for criminal group context, police operations, off-duty police
perpetrator, and political victim fields on unique_event.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, Sequence[str], None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = [
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


def upgrade() -> None:
    with op.batch_alter_table("unique_event", schema=None) as batch_op:
        for name, col_type, indexed in _NEW_COLUMNS:
            batch_op.add_column(sa.Column(name, col_type, nullable=True))
            if indexed:
                batch_op.create_index(batch_op.f(f"ix_unique_event_{name}"), [name], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("unique_event", schema=None) as batch_op:
        for name, _, indexed in reversed(_NEW_COLUMNS):
            if indexed:
                batch_op.drop_index(batch_op.f(f"ix_unique_event_{name}"))
            batch_op.drop_column(name)
