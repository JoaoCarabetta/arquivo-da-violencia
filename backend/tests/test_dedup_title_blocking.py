"""Tests for dedup title fuzzy blocking (AQV-38)."""

from datetime import datetime

import pytest

from app.services.enrichment import (
    FUZZY_TITLE_THRESHOLD,
    LLM_MATCH_CONFIDENCE_THRESHOLD,
    TITLE_DATE_TOLERANCE_DAYS,
    block_by_title_fuzzy,
    fuzzy_title_match,
    normalize_title,
)


def test_normalize_title_strips_accents_and_case():
    assert normalize_title("  Homicídio em Juiz de Fora  ") == "homicidio em juiz de fora"


def test_fuzzy_title_match_exact():
    title = "Tiroteio deixa dois mortos na Zona Norte"
    assert fuzzy_title_match(title, title)


def test_fuzzy_title_match_similar_headlines():
    a = "Homem é morto a tiros em operação policial no Rio"
    b = "Homem morto a tiros em operacao policial no Rio de Janeiro"
    assert fuzzy_title_match(a, b, threshold=0.85)


def test_fuzzy_title_match_rejects_unrelated():
    a = "CVLI: estado registra 4.241 mortes violentas em 2025"
    b = "Homem é morto a tiros em operação policial no Rio"
    assert not fuzzy_title_match(a, b, threshold=FUZZY_TITLE_THRESHOLD)


def test_fuzzy_title_match_rejects_short_substring_only():
    """Unrelated headlines where one title is a short substring of another."""
    a = "CVLI"
    b = "CVLI: estado registra mortes violentas em 2025"
    assert not fuzzy_title_match(a, b, threshold=FUZZY_TITLE_THRESHOLD)


def test_tuned_constants():
    assert TITLE_DATE_TOLERANCE_DAYS == 3
    assert FUZZY_TITLE_THRESHOLD == 0.80
    assert LLM_MATCH_CONFIDENCE_THRESHOLD == 0.6


def test_fuzzy_title_match_sao_jose_feminicidio_pair():
    """Regression: prod duplicate pair 9843/9851 (same incident, different headlines)."""
    a = "HOMICÍDIO - VIA PÚBLICA SERTÃO DO MARUIM - 06/07/2026"
    b = "FEMINICÍDIO - RODOVIA SC-281, SERTÃO DO MARUIM - 06/07/2026"
    assert fuzzy_title_match(a, b, threshold=FUZZY_TITLE_THRESHOLD)


@pytest.mark.asyncio
async def test_block_by_title_fuzzy_finds_similar_event(async_session):
    from app.models.unique_event import UniqueEvent
    from app.models.raw_event import RawEvent

    unique = UniqueEvent(
        title="Tiroteio deixa dois mortos na Zona Norte do Rio",
        event_date=datetime(2025, 1, 15),
        city="Rio de Janeiro",
        state="RJ",
        victim_count=2,
        source_count=1,
    )
    async_session.add(unique)
    await async_session.commit()
    await async_session.refresh(unique)

    raw = RawEvent(
        title="Tiroteio deixa 2 mortos na Zona Norte",
        event_date=datetime(2025, 1, 16),
        city="Rio de Janeiro",
        state="RJ",
        victim_count=2,
        source_google_news_id=1,
    )

    from unittest.mock import patch

    class _TestSessionMaker:
        def __init__(self, session):
            self._session = session

        def __call__(self):
            return self

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch("app.services.enrichment.async_session_maker", _TestSessionMaker(async_session)):
        candidates = await block_by_title_fuzzy(raw)

    assert len(candidates) == 1
    assert candidates[0].id == unique.id


@pytest.mark.asyncio
async def test_block_by_title_fuzzy_respects_date_window(async_session):
    from app.models.unique_event import UniqueEvent
    from app.models.raw_event import RawEvent
    from unittest.mock import patch

    unique = UniqueEvent(
        title="Homicidio em Juiz de Fora deixa um morto",
        event_date=datetime(2025, 1, 1),
        city="Juiz de Fora",
        state="MG",
        victim_count=1,
        source_count=1,
    )
    async_session.add(unique)
    await async_session.commit()

    raw = RawEvent(
        title="Homicidio em Juiz de Fora deixa um morto",
        event_date=datetime(2025, 1, 10),
        city="Juiz de Fora",
        state="MG",
        victim_count=1,
        source_google_news_id=1,
    )

    class _TestSessionMaker:
        def __init__(self, session):
            self._session = session

        def __call__(self):
            return self

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch("app.services.enrichment.async_session_maker", _TestSessionMaker(async_session)):
        candidates = await block_by_title_fuzzy(raw)

    assert candidates == []
