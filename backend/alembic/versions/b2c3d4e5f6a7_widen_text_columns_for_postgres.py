"""widen_text_columns_for_postgres

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-06 20:50:00.000000

SQLite does not enforce VARCHAR length limits; production data exceeds several
Postgres column bounds. Widen bounded string columns to TEXT before SQLite→PG
data import.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs that must accept long LLM/extraction strings on Postgres.
_TEXT_COLUMNS: list[tuple[str, str]] = [
    # source_google_news
    ("source_google_news", "google_news_id"),
    ("source_google_news", "google_news_url"),
    ("source_google_news", "resolved_url"),
    ("source_google_news", "headline"),
    ("source_google_news", "publisher_name"),
    ("source_google_news", "publisher_url"),
    ("source_google_news", "search_query"),
    # unique_event
    ("unique_event", "homicide_type"),
    ("unique_event", "method_of_death"),
    ("unique_event", "date_precision"),
    ("unique_event", "time_of_day"),
    ("unique_event", "country"),
    ("unique_event", "state"),
    ("unique_event", "city"),
    ("unique_event", "neighborhood"),
    ("unique_event", "street"),
    ("unique_event", "establishment"),
    ("unique_event", "full_location_description"),
    ("unique_event", "plus_code"),
    ("unique_event", "place_id"),
    ("unique_event", "formatted_address"),
    ("unique_event", "location_precision"),
    ("unique_event", "geocoding_source"),
    ("unique_event", "victims_summary"),
    ("unique_event", "title"),
    ("unique_event", "chronological_description"),
    ("unique_event", "additional_context"),
    ("unique_event", "enrichment_model"),
    ("unique_event", "content_class"),
    # raw_event
    ("raw_event", "homicide_type"),
    ("raw_event", "method_of_death"),
    ("raw_event", "date_precision"),
    ("raw_event", "time_of_day"),
    ("raw_event", "city"),
    ("raw_event", "state"),
    ("raw_event", "neighborhood"),
    ("raw_event", "title"),
    ("raw_event", "chronological_description"),
    ("raw_event", "extraction_model"),
    ("raw_event", "extraction_error"),
    ("raw_event", "deduplication_status"),
    ("raw_event", "content_class"),
    # city_stats
    ("city_stats", "city_name"),
    # pipeline_attempt
    ("pipeline_attempt", "stage"),
    ("pipeline_attempt", "outcome"),
    ("pipeline_attempt", "failure_reason"),
    ("pipeline_attempt", "failure_detail"),
    ("pipeline_attempt", "url_domain"),
    ("pipeline_attempt", "model"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, column in _TEXT_COLUMNS:
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT")
        )


def downgrade() -> None:
    # Irreversible: imported data may exceed original VARCHAR limits.
    pass
