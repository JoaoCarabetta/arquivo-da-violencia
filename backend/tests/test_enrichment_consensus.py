"""Tests for enrichment raw-field consensus and pre-cluster title overlap."""

from datetime import datetime

from app.models.raw_event import RawEvent
from app.services.enrichment import (
    EnrichmentResult,
    apply_raw_field_consensus,
    fuzzy_title_match,
    pre_cluster_by_victim_name,
)


class _Row:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_pre_cluster_title_overlap_without_victim_names():
    a = RawEvent(
        id=1,
        title="FEMINICÍDIO - RESIDÊNCIA CARAJÁS - 04/07/2026",
        event_date=datetime(2026, 7, 4),
        city="Contagem",
        source_google_news_id=1,
    )
    b = RawEvent(
        id=2,
        title="FEMINICÍDIO - RESIDÊNCIA BAIRRO CARAJÁS - 04/07/2026",
        event_date=datetime(2026, 7, 4),
        city="Contagem",
        source_google_news_id=2,
    )
    assert fuzzy_title_match(a.title, b.title)
    clusters = pre_cluster_by_victim_name([a, b])
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_apply_raw_field_consensus_victim_count_majority():
    result = EnrichmentResult(
        title="Test",
        event_date="2026-07-03",
        city="São Paulo",
        state="SP",
        neighborhood=None,
        street=None,
        victims_summary="Two people",
        victim_count=2,
        chronological_description="desc",
    )
    rows = [
        _Row(victim_count=1, city="São Paulo"),
        _Row(victim_count=1, city="São Paulo"),
        _Row(victim_count=2, city="São Paulo"),
    ]
    merged = apply_raw_field_consensus(result, rows)
    assert merged.victim_count == 1


def test_apply_raw_field_consensus_city_majority():
    result = EnrichmentResult(
        title="Test",
        event_date="2026-07-03",
        city="Wrong City",
        state="AC",
        neighborhood=None,
        street=None,
        victims_summary=None,
        victim_count=1,
        chronological_description="desc",
    )
    rows = [
        _Row(victim_count=1, city="Rio Branco"),
        _Row(victim_count=2, city="Rio Branco"),
    ]
    merged = apply_raw_field_consensus(result, rows)
    assert merged.city == "Rio Branco"
