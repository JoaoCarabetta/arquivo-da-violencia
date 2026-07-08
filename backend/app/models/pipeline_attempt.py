"""Pipeline attempt log - one row per stage attempt (success or failure).

This is the diagnostics backbone: every download/extraction attempt records its
outcome and, on failure, a classified reason plus enough context (HTTP status,
domain, model, content length, duration) to analyze WHY the pipeline loses items.
Unlike the terminal ``failed_in_*`` statuses on ``source_google_news`` (which keep
only the latest state and no reason), this table keeps full history for trend
analysis and retry accounting.
"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class PipelineAttemptBase(SQLModel):
    """Base model for a pipeline stage attempt."""

    # Which item/stage this attempt is about
    source_google_news_id: int | None = Field(
        default=None, foreign_key="source_google_news.id", index=True
    )
    raw_event_id: int | None = Field(default=None, index=True)

    stage: str = Field(max_length=20, index=True)  # download | content_gate | extraction
    outcome: str = Field(max_length=20, index=True)  # success | failure | discarded

    # Failure classification (null on success)
    failure_reason: str | None = Field(default=None, max_length=40, index=True)
    failure_detail: str | None = Field(default=None, max_length=1000)

    # Download diagnostics
    http_status: int | None = Field(default=None)
    url_domain: str | None = Field(default=None, max_length=256, index=True)

    # Extraction diagnostics
    model: str | None = Field(default=None, max_length=50)
    content_length: int | None = Field(default=None)

    # Common metrics
    duration_ms: int | None = Field(default=None)
    attempt_number: int = Field(default=1)


class PipelineAttempt(PipelineAttemptBase, table=True):
    """Pipeline stage attempt record."""

    __tablename__ = "pipeline_attempt"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class PipelineAttemptRead(PipelineAttemptBase):
    """Schema for reading a pipeline attempt."""

    id: int
    created_at: datetime
