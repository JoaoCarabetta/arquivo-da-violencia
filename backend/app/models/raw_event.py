"""Raw event model - extracted from any source."""

from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON


# Type definitions matching the extraction schema
HomicideType = Literal[
    "Homicídio",
    "Homicídio Qualificado",
    "Homicídio Culposo",
    "Tentativa de Homicídio",
    "Latrocínio",
    "Feminicídio",
    "Infanticídio",
    "Outro"
]

MethodOfDeath = Literal[
    "Arma de fogo",
    "Arma branca",
    "Estrangulamento",
    "Asfixia",
    "Espancamento",
    "Atropelamento",
    "Envenenamento",
    "Objeto contundente",
    "Incêndio",
    "Queda",
    "Outro",
    "Não especificado"
]


class RawEventBase(SQLModel):
    """Base model for raw extracted events."""
    
    # === Key queryable fields (denormalized for efficient queries) ===
    
    # Event classification
    homicide_type: str | None = Field(default=None, max_length=50, index=True)
    method_of_death: str | None = Field(default=None, max_length=50)
    
    # Date/time (extracted, may be null if not explicitly in text)
    event_date: datetime | None = Field(default=None, index=True)
    date_precision: str | None = Field(default=None, max_length=20)  # exata, parcial, não informada
    time_of_day: str | None = Field(default=None, max_length=20)
    
    # Location (key fields for filtering)
    city: str | None = Field(default=None, max_length=100, index=True)
    state: str | None = Field(default=None, max_length=50)
    neighborhood: str | None = Field(default=None, max_length=100)
    
    # Victim counts
    victim_count: int | None = Field(default=None)
    identified_victim_count: int | None = Field(default=None)
    
    # Perpetrator counts
    perpetrator_count: int | None = Field(default=None)
    security_force_involved: bool | None = Field(default=None, index=True)
    
    # Summary fields
    title: str | None = Field(default=None, max_length=512)
    chronological_description: str | None = Field(default=None)
    
    # === Full structured extraction (JSON) ===
    # Stores the complete ViolentDeathEvent as JSON for detailed access
    extraction_data: dict | None = Field(default=None, sa_column=Column(JSON))
    
    # === Extraction metadata ===
    extraction_model: str | None = Field(default=None, max_length=50)  # e.g., "gemini-2.5-flash"
    extraction_success: bool = Field(default=True)
    extraction_error: str | None = Field(default=None)
    
    # === Deduplication status ===
    # pending: awaiting deduplication
    # matched: linked to existing UniqueEvent
    # clustered: grouped with other RawEvents into new UniqueEvent
    deduplication_status: str = Field(default="pending", max_length=20, index=True)


class RawEvent(RawEventBase, table=True):
    """Raw event extracted from a source."""
    
    __tablename__ = "raw_event"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # Foreign keys
    source_google_news_id: int | None = Field(
        default=None, 
        foreign_key="source_google_news.id",
        index=True
    )
    unique_event_id: int | None = Field(
        default=None, 
        foreign_key="unique_event.id",
        index=True
    )
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RawEventCreate(RawEventBase):
    """Schema for creating a raw event."""
    
    source_google_news_id: int


class RawEventRead(RawEventBase):
    """Schema for reading a raw event."""
    
    id: int
    source_google_news_id: int | None
    unique_event_id: int | None
    deduplication_status: str
    created_at: datetime
    updated_at: datetime
