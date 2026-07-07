"""Tests for victim name extraction fallbacks and fuzzy pre-clustering."""

from datetime import datetime

from app.models.raw_event import RawEvent
from app.services.enrichment import (
    extract_victim_names,
    fuzzy_name_match,
    pre_cluster_by_victim_name,
)


def test_extract_victim_names_from_description_when_json_empty():
    raw = RawEvent(
        title="Feminicídio em Confresa",
        chronological_description=(
            "A vítima Daiany Rodrigues de Souza, 33 anos, foi morta a facadas "
            "pelo namorado José da Cruz Evangelista em um bar."
        ),
        extraction_data={"victims": {"identifiable_victims": []}},
        source_google_news_id=1,
    )
    names = extract_victim_names(raw)
    assert any("daiany" in n for n in names)


def test_pre_cluster_fuzzy_victim_name():
    a = RawEvent(
        id=1,
        title="Event A",
        event_date=datetime(2026, 7, 4),
        city="Confresa",
        extraction_data={
            "victims": {"identifiable_victims": [{"name": "João da Silva"}]}
        },
        source_google_news_id=1,
    )
    b = RawEvent(
        id=2,
        title="Event B",
        event_date=datetime(2026, 7, 4),
        city="Confresa",
        extraction_data={
            "victims": {"identifiable_victims": [{"name": "João Silva"}]}
        },
        source_google_news_id=2,
    )
    clusters = pre_cluster_by_victim_name([a, b])
    assert len(clusters) == 1
    assert len(clusters[0]) == 2
    assert fuzzy_name_match("João da Silva", "João Silva")
