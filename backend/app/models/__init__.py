"""SQLModel database models."""

from app.models.source_google_news import (
    SourceGoogleNews,
    SourceGoogleNewsBase,
    SourceGoogleNewsCreate,
    SourceGoogleNewsRead,
    SourceStatus,
)
from app.models.raw_event import (
    RawEvent,
    RawEventBase,
    RawEventCreate,
    RawEventRead,
    RawEventUpdate,
)
from app.models.unique_event import (
    UniqueEvent,
    UniqueEventBase,
    UniqueEventCreate,
    UniqueEventRead,
)
from app.models.city_stats import (
    CityStats,
    CityStatsBase,
    CityStatsRead,
)

__all__ = [
    # Source Google News
    "SourceGoogleNews",
    "SourceGoogleNewsBase",
    "SourceGoogleNewsCreate",
    "SourceGoogleNewsRead",
    "SourceStatus",
    # Raw Event
    "RawEvent",
    "RawEventBase",
    "RawEventCreate",
    "RawEventRead",
    "RawEventUpdate",
    # Unique Event
    "UniqueEvent",
    "UniqueEventBase",
    "UniqueEventCreate",
    "UniqueEventRead",
    # City Stats
    "CityStats",
    "CityStatsBase",
    "CityStatsRead",
]
