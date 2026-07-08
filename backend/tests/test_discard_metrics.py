"""Tests for content-filter discard taxonomy and metrics gauges."""

from app.metrics import pipeline_attempt_discards_24h, pipeline_attempt_failures_24h, set_pipeline_inventory_metrics
from app.services import diagnostics


def test_content_filter_reasons_include_llm_reject():
    assert diagnostics.LLM_CONTENT_REJECT in diagnostics.CONTENT_FILTER_REASONS
    assert diagnostics.is_content_filter_reason(diagnostics.LLM_CONTENT_REJECT)
    assert diagnostics.is_content_filter_reason(diagnostics.AGGREGATE_CONTENT)
    assert not diagnostics.is_content_filter_reason(diagnostics.FETCH_BLOCKED)
    assert not diagnostics.is_content_filter_reason(None)


def test_set_pipeline_inventory_metrics_splits_failures_and_discards():
    set_pipeline_inventory_metrics(
        status_counts={},
        stuck_counts={},
        failure_counts={("download", "fetch_timeout"): 3},
        discard_counts={
            ("content_gate", "llm_content_reject"): 5,
            ("content_gate", "aggregate_content"): 2,
        },
        sources_total=0,
        violent_death=0,
        raw_events_total=0,
        unique_events_total=0,
    )

    assert (
        pipeline_attempt_failures_24h.labels(
            stage="download", failure_reason="fetch_timeout"
        )._value.get()
        == 3.0
    )
    assert (
        pipeline_attempt_discards_24h.labels(
            stage="content_gate", failure_reason="llm_content_reject"
        )._value.get()
        == 5.0
    )
    assert (
        pipeline_attempt_discards_24h.labels(
            stage="content_gate", failure_reason="aggregate_content"
        )._value.get()
        == 2.0
    )

    # Stale discard labels are zeroed when absent from the next refresh.
    set_pipeline_inventory_metrics(
        status_counts={},
        stuck_counts={},
        failure_counts={("download", "fetch_timeout"): 3},
        discard_counts={("content_gate", "llm_content_reject"): 1},
        sources_total=0,
        violent_death=0,
        raw_events_total=0,
        unique_events_total=0,
    )
    assert (
        pipeline_attempt_discards_24h.labels(
            stage="content_gate", failure_reason="aggregate_content"
        )._value.get()
        == 0.0
    )
