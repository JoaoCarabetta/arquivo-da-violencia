"""Unique event model - deduplicated canonical event with geolocation."""

from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON


class UniqueEventBase(SQLModel):
    """Base model for unique/deduplicated events."""
    
    # === Event classification ===
    homicide_type: str | None = Field(default=None, max_length=50, index=True)
    method_of_death: str | None = Field(default=None, max_length=50)
    
    # === Date/time ===
    event_date: datetime | None = Field(default=None, index=True)
    date_precision: str | None = Field(default=None, max_length=20)
    time_of_day: str | None = Field(default=None, max_length=20)
    
    # === Location (extracted) ===
    country: str | None = Field(default="Brasil", max_length=100)
    state: str | None = Field(default=None, max_length=50, index=True)
    city: str | None = Field(default=None, max_length=100, index=True)
    neighborhood: str | None = Field(default=None, max_length=100)
    street: str | None = Field(default=None, max_length=256)
    establishment: str | None = Field(default=None, max_length=256)
    full_location_description: str | None = Field(default=None)
    
    # === Google Maps Geolocation ===
    latitude: Decimal | None = Field(default=None, max_digits=10, decimal_places=8)
    longitude: Decimal | None = Field(default=None, max_digits=11, decimal_places=8)
    plus_code: str | None = Field(default=None, max_length=20)  # e.g., "589C+W5 Rio de Janeiro"
    place_id: str | None = Field(default=None, max_length=256)  # Google Maps place_id
    formatted_address: str | None = Field(default=None, max_length=512)  # Full formatted address from Google
    location_precision: str | None = Field(default=None, max_length=50)  # exact, approximate, neighborhood_center, city_center
    geocoding_source: str | None = Field(default=None, max_length=50)  # google_maps, manual, etc.
    geocoding_confidence: float | None = Field(default=None)  # 0.0 to 1.0
    
    # === Victim information ===
    victim_count: int | None = Field(default=None)
    identified_victim_count: int | None = Field(default=None)
    victims_summary: str | None = Field(default=None)  # e.g., "João Silva, 32 anos, masculino"
    
    # === Perpetrator information ===
    perpetrator_count: int | None = Field(default=None)
    identified_perpetrator_count: int | None = Field(default=None)
    security_force_involved: bool | None = Field(default=None, index=True)
    
    # === Summary fields ===
    title: str | None = Field(default=None, max_length=512)
    chronological_description: str | None = Field(default=None)
    additional_context: str | None = Field(default=None)
    
    # === Full structured data (JSON) ===
    # Merged/enriched data from all linked RawEvents
    merged_data: dict | None = Field(default=None, sa_column=Column(JSON))
    
    # === Source tracking ===
    source_count: int = Field(default=1)  # Number of RawEvents linked to this
    
    # === Status ===
    confirmed: bool = Field(default=False)  # Manual review status


class UniqueEvent(UniqueEventBase, table=True):
    """Unique/deduplicated event record."""
    
    __tablename__ = "unique_event"
    
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UniqueEventCreate(UniqueEventBase):
    """Schema for creating a unique event."""
    pass


class UniqueEventRead(UniqueEventBase):
    """Schema for reading a unique event."""
    
    id: int
    created_at: datetime
    updated_at: datetime
