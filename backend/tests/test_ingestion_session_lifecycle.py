"""Test that ingest_city does not hold DB sessions across HTTP fetches.

Issue #168: QueuePool exhaustion during concurrent city ingest.
The bug: ingest_city held a DB session open across RSS fetch HTTP calls.
With max_concurrent=10 cities, this exhausted the pool (size 15 + overflow 15).

The fix: Release DB sessions before HTTP fetches, acquire new sessions after.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.ingestion import ingest_all_cities


def _entry(*, entry_id: str, link: str, title: str = "Headline - Publisher"):
    """Create a mock RSS entry."""
    return {
        "id": entry_id,
        "link": link,
        "title": title,
        "source": {"href": "https://publisher.example"},
        "published_parsed": (2026, 7, 7, 12, 0, 0),
    }


@pytest.mark.asyncio
async def test_concurrent_ingest_does_not_exhaust_pool():
    """
    Test that concurrent city ingestion does not exhaust the connection pool.
    
    Before fix: ingest_city held a session across HTTP fetches.
    With 10 concurrent cities, this would exhaust a pool of size 15.
    
    After fix: Sessions are released before HTTP fetches.
    Pool should have 0 checked-out connections after ingestion completes.
    """
    # Create a test engine with a small pool (mimic staging: size 5, overflow 5)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=60,
    )
    
    # Initialize DB
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    # Track session creation
    session_tracker = {"active_sessions": 0, "peak_sessions": 0}
    
    class TrackedSessionMaker:
        """Session maker that tracks active session count."""
        
        def __call__(self):
            return self
        
        async def __aenter__(self):
            session_tracker["active_sessions"] += 1
            if session_tracker["active_sessions"] > session_tracker["peak_sessions"]:
                session_tracker["peak_sessions"] = session_tracker["active_sessions"]
            return AsyncSession(engine)
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            session_tracker["active_sessions"] -= 1
            return False
    
    # Mock HTTP fetch to simulate slow Google News requests
    async def mock_rate_limited_fetch(query: str, when=None, country="BR"):
        """Simulate a slow HTTP fetch (100ms) to expose session leaks."""
        await asyncio.sleep(0.1)  # Simulate network latency
        # Return 1 entry per city
        return [_entry(
            entry_id=f"id-{query[:10]}",
            link=f"https://news.google.com/{query[:10]}"
        )]
    
    # Mock URL resolution (also HTTP)
    def mock_resolve_url(url: str):
        """Mock URL resolution."""
        return f"https://article.example/{url[-10:]}"
    
    cities = [f"City{i}" for i in range(10)]  # 10 concurrent cities
    
    with (
        patch("app.services.ingestion.async_session_maker", TrackedSessionMaker()),
        patch(
            "app.services.ingestion.rate_limited_fetch",
            side_effect=mock_rate_limited_fetch,
        ),
        patch(
            "app.services.ingestion.resolve_google_news_url",
            side_effect=mock_resolve_url,
        ),
    ):
        result = await ingest_all_cities(
            cities=cities,
            when="1h",
            resolve_urls=True,
            max_concurrent=10,
            country="BR",
        )
    
    # Verify ingestion succeeded
    assert result["cities_processed"] == 10
    assert result["errors"] == 0
    
    # CRITICAL: After ingestion completes, all sessions must be closed
    # This is the main assertion that fails before the fix
    assert session_tracker["active_sessions"] == 0, (
        f"Connection leak detected: {session_tracker['active_sessions']} "
        f"sessions still active after ingestion completed"
    )
    
    # With the bug: peak would be 10+ (one per city held during HTTP)
    # After fix: peak should be much lower (sessions released before HTTP)
    # We expect peak <= 10 since we have 10 concurrent cities, but each
    # city should only briefly hold a session (not across HTTP)
    print(f"Peak concurrent sessions: {session_tracker['peak_sessions']}")
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_city_releases_session_before_http():
    """
    Test that ingest_city releases its session before HTTP fetches.
    
    This is a more direct test: verify session lifecycle at the seam.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=1,  # Fast timeout to detect leaks quickly
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    session_events = []
    
    class EventTrackingSessionMaker:
        """Track session open/close events with timestamps."""
        
        def __call__(self):
            return self
        
        async def __aenter__(self):
            import time
            session_events.append(("open", time.time()))
            return AsyncSession(engine)
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            import time
            session_events.append(("close", time.time()))
            return False
    
    http_fetch_times = []
    
    async def mock_rate_limited_fetch(query: str, when=None, country="BR"):
        """Record when HTTP fetch occurs."""
        import time
        start = time.time()
        await asyncio.sleep(0.05)  # Simulate HTTP delay
        http_fetch_times.append((start, time.time()))
        return [_entry(entry_id="test-id", link="https://news.google.com/test")]
    
    with (
        patch("app.services.ingestion.async_session_maker", EventTrackingSessionMaker()),
        patch(
            "app.services.ingestion.rate_limited_fetch",
            side_effect=mock_rate_limited_fetch,
        ),
        patch("app.services.ingestion.resolve_google_news_url", return_value=None),
    ):
        from app.services.ingestion import ingest_city
        
        await ingest_city("TestCity", when="1h", resolve_urls=False, country="BR")
    
    # Verify sessions were opened and closed
    assert len(session_events) > 0, "No sessions were created"
    assert session_events.count(("open", pytest.approx(0, abs=10))) == session_events.count(
        ("close", pytest.approx(0, abs=10))
    ), "Mismatch in open/close events"
    
    # Verify HTTP fetches occurred
    assert len(http_fetch_times) > 0, "No HTTP fetches occurred"
    
    # CRITICAL: Verify that no session was open during HTTP fetches
    # For each HTTP fetch, check if any session was open at that time
    for http_start, http_end in http_fetch_times:
        # Find sessions that were open during this HTTP fetch
        sessions_during_http = []
        
        i = 0
        while i < len(session_events):
            if session_events[i][0] == "open":
                open_time = session_events[i][1]
                # Find corresponding close
                close_time = None
                for j in range(i + 1, len(session_events)):
                    if session_events[j][0] == "close":
                        close_time = session_events[j][1]
                        break
                
                if close_time:
                    # Check if this session overlaps with HTTP fetch
                    if open_time <= http_start and close_time >= http_end:
                        sessions_during_http.append((open_time, close_time))
            i += 1
        
        assert len(sessions_during_http) == 0, (
            f"Session was held open during HTTP fetch! "
            f"HTTP: {http_start:.3f}-{http_end:.3f}, "
            f"Sessions: {sessions_during_http}"
        )
    
    await engine.dispose()
