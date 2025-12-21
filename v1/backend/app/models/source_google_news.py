"""Google News source model."""

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class SourceStatus(str, Enum):
    """Status of a source in the pipeline."""
    
    pending = "pending"
    downloaded = "downloaded"
    processed = "processed"
    failed = "failed"
    ignored = "ignored"


class SourceGoogleNewsBase(SQLModel):
    """Base model for Google News sources."""
    
    # Google News specific fields (IDs can be very long base64 encoded strings)
    google_news_id: str = Field(unique=True, index=True)
    google_news_url: str = Field()
    
    # Resolved article URL (after decoding the obfuscated link)
    resolved_url: str | None = Field(default=None, max_length=2048)
    
    # Article metadata
    headline: str | None = Field(default=None, max_length=512)
    
    # Publisher info (from RSS source tag)
    publisher_name: str | None = Field(default=None, max_length=256)
    publisher_url: str | None = Field(default=None, max_length=512)
    
    # Article content (extracted via trafilatura)
    content: str | None = Field(default=None)
    
    # Dates
    published_at: datetime | None = Field(default=None, index=True)
    
    # Search context (which query found this)
    search_query: str | None = Field(default=None, max_length=256)
    
    # Pipeline status
    status: SourceStatus = Field(default=SourceStatus.pending, index=True)


class SourceGoogleNews(SourceGoogleNewsBase, table=True):
    """Google News source record."""
    
    __tablename__ = "source_google_news"
    
    id: int | None = Field(default=None, primary_key=True)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SourceGoogleNewsCreate(SourceGoogleNewsBase):
    """Schema for creating a source."""
    pass


class SourceGoogleNewsRead(SourceGoogleNewsBase):
    """Schema for reading a source."""
    
    id: int
    fetched_at: datetime
    updated_at: datetime
