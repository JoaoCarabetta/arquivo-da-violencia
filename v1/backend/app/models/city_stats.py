"""City statistics model for tracking ingestion and sharding status."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class CityStatsBase(SQLModel):
    """Base model for city statistics."""
    
    city_name: str = Field(unique=True, index=True, max_length=256)
    
    # Sharding flag - when True, queries are split by news source
    needs_sharding: bool = Field(default=False)
    
    # Last fetch statistics
    last_result_count: int = Field(default=0)
    
    # How many times this city has hit the 100 result limit
    hit_limit_count: int = Field(default=0)
    
    # When was this city last fetched
    last_fetch_at: datetime | None = Field(default=None)


class CityStats(CityStatsBase, table=True):
    """City statistics record for tracking ingestion behavior."""
    
    __tablename__ = "city_stats"
    
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CityStatsRead(CityStatsBase):
    """Schema for reading city stats."""
    
    id: int
    created_at: datetime
    updated_at: datetime

