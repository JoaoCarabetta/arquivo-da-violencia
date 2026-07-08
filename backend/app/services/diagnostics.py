"""Pipeline diagnostics: failure taxonomy and attempt logging.

Every download/extraction attempt should call :func:`record_attempt` so we build a
queryable history of what succeeds and what fails (and why). Failure reasons are
classified into a small, stable taxonomy and split into transient (worth
retrying) vs permanent (do not retry).

All writes here are best-effort: a logging failure must never break the pipeline.
"""

from __future__ import annotations

from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import text

from app.database import async_session_maker


# === Stages ===
STAGE_DOWNLOAD = "download"
STAGE_CONTENT_GATE = "content_gate"
STAGE_EXTRACTION = "extraction"

# === Outcomes ===
OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"

# === Download failure reasons ===
FETCH_TIMEOUT = "fetch_timeout"
FETCH_BLOCKED = "fetch_blocked"  # 401/403/429 - bot/anti-scraping
FETCH_NOT_FOUND = "fetch_not_found"  # 404/410
FETCH_SERVER_ERROR = "fetch_server_error"  # 5xx
FETCH_NETWORK_ERROR = "fetch_network_error"  # DNS, connection reset, SSL, etc.
EMPTY_CONTENT = "empty_content"  # HTTP 200 but no extractable article text
NO_URL = "no_url"  # source has no usable URL

# === Content gate failure / discard reasons ===
AGGREGATE_CONTENT = "aggregate_content"
FOREIGN_CONTENT = "foreign_content"
NON_INCIDENT_CONTENT = "non_incident_content"
LLM_CONTENT_REJECT = "llm_content_reject"

# === Extraction failure reasons ===
LLM_RATE_LIMIT = "llm_rate_limit"  # 429 / RESOURCE_EXHAUSTED (short-term)
LLM_QUOTA = "llm_quota"  # daily/project quota exhausted
LLM_TIMEOUT = "llm_timeout"
LLM_SAFETY_BLOCK = "llm_safety_block"  # response blocked by safety filters
CONTENT_TOO_LONG = "content_too_long"  # INPUT exceeds the model's context window
LLM_MAX_TOKENS = "llm_max_tokens"  # OUTPUT truncated: model hit its output-token cap
VALIDATION_ERROR = "validation_error"  # instructor/pydantic schema validation
EMPTY_EXTRACTION = "empty_extraction"  # model returned nothing usable
LLM_UNKNOWN = "llm_unknown"

# Reasons that are worth retrying later (infra/throughput, not data-quality).
TRANSIENT_REASONS = frozenset(
    {
        FETCH_TIMEOUT,
        FETCH_SERVER_ERROR,
        FETCH_NETWORK_ERROR,
        FETCH_BLOCKED,  # often rate-based; a later retry can succeed
        LLM_RATE_LIMIT,
        LLM_QUOTA,
        LLM_TIMEOUT,
    }
)


def is_transient(reason: str | None) -> bool:
    """Whether a failure reason is worth retrying."""
    return reason in TRANSIENT_REASONS


def domain_of(url: str | None) -> str | None:
    """Extract a bare hostname (no www) from a URL for grouping."""
    if not url:
        return None
    try:
        host = urlparse(url).hostname
        if not host:
            return None
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return None


def classify_http_status(status: int) -> str:
    """Map an HTTP status code to a download failure reason."""
    if status in (401, 403, 429):
        return FETCH_BLOCKED
    if status in (404, 410):
        return FETCH_NOT_FOUND
    if status >= 500:
        return FETCH_SERVER_ERROR
    # Other 4xx and unexpected codes: treat as network/transport-level oddity.
    return FETCH_NETWORK_ERROR


def classify_download_exception(exc: Exception) -> str:
    """Map an exception raised during fetch to a download failure reason."""
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return FETCH_TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        return classify_http_status(exc.response.status_code)
    if isinstance(exc, httpx.HTTPError):
        return FETCH_NETWORK_ERROR
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return FETCH_TIMEOUT
    return FETCH_NETWORK_ERROR


def classify_extraction_exception(exc: Exception) -> str:
    """Map an exception raised during LLM extraction to a failure reason.

    Gemini/instructor surface most problems as generic exceptions, so we inspect
    the type name and message text heuristically.
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()

    # OUTPUT truncation: the model produced a response but ran into its output
    # token cap (finish_reason == "length"). instructor raises
    # IncompleteOutputException ("...incomplete due to a max_tokens length limit").
    # Check this first: its message contains "max_tokens"/"limit" and would
    # otherwise be misread as an input-size problem.
    if (
        "incompleteoutput" in name
        or "output is incomplete" in msg
        or "max_tokens length limit" in msg
        or ("incomplete" in msg and "max_tokens" in msg)
    ):
        return LLM_MAX_TOKENS
    if "validation" in name or "validationerror" in name:
        return VALIDATION_ERROR
    if "429" in msg or "resource_exhausted" in msg or "rate limit" in msg or "ratelimit" in name:
        # Distinguish hard daily quota from short-term rate limiting when possible.
        if "quota" in msg or "per day" in msg or "daily" in msg:
            return LLM_QUOTA
        return LLM_RATE_LIMIT
    if "quota" in msg:
        return LLM_QUOTA
    if "timeout" in name or "timeout" in msg or "deadline" in msg:
        return LLM_TIMEOUT
    if "safety" in msg or "blocked" in msg or "recitation" in msg or "prohibited" in msg:
        return LLM_SAFETY_BLOCK
    # INPUT too long: the prompt/context exceeds the model's input window.
    if (
        "context length" in msg
        or "context window" in msg
        or "too long" in msg
        or "input is too large" in msg
        or ("input" in msg and "token" in msg and ("exceed" in msg or "max" in msg or "limit" in msg))
    ):
        return CONTENT_TOO_LONG
    if "validation" in msg:
        return VALIDATION_ERROR
    return LLM_UNKNOWN


async def count_attempts(source_google_news_id: int, stage: str) -> int:
    """Number of prior attempts logged for a source at a given stage."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM pipeline_attempt
                    WHERE source_google_news_id = :sid AND stage = :stage
                    """
                ),
                {"sid": source_google_news_id, "stage": stage},
            )
            return int(result.scalar() or 0)
    except Exception as e:  # pragma: no cover - best effort
        logger.debug(f"count_attempts failed: {e}")
        return 0


async def record_attempt(
    *,
    stage: str,
    outcome: str,
    source_google_news_id: int | None = None,
    raw_event_id: int | None = None,
    failure_reason: str | None = None,
    failure_detail: str | None = None,
    http_status: int | None = None,
    url_domain: str | None = None,
    model: str | None = None,
    content_length: int | None = None,
    duration_ms: int | None = None,
    attempt_number: int = 1,
) -> None:
    """Write one pipeline_attempt row. Best-effort: never raises."""
    detail = failure_detail[:1000] if failure_detail else None
    try:
        async with async_session_maker() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO pipeline_attempt (
                        source_google_news_id, raw_event_id, stage, outcome,
                        failure_reason, failure_detail, http_status, url_domain,
                        model, content_length, duration_ms, attempt_number, created_at
                    ) VALUES (
                        :source_google_news_id, :raw_event_id, :stage, :outcome,
                        :failure_reason, :failure_detail, :http_status, :url_domain,
                        :model, :content_length, :duration_ms, :attempt_number, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "source_google_news_id": source_google_news_id,
                    "raw_event_id": raw_event_id,
                    "stage": stage,
                    "outcome": outcome,
                    "failure_reason": failure_reason,
                    "failure_detail": detail,
                    "http_status": http_status,
                    "url_domain": url_domain,
                    "model": model,
                    "content_length": content_length,
                    "duration_ms": duration_ms,
                    "attempt_number": attempt_number,
                },
            )
            await session.commit()
    except Exception as e:  # pragma: no cover - logging must not break pipeline
        logger.warning(f"Failed to record pipeline_attempt ({stage}/{outcome}): {e}")

    try:
        from app.metrics import record_attempt_metrics

        record_attempt_metrics(
            stage=stage,
            outcome=outcome,
            failure_reason=failure_reason,
            duration_ms=duration_ms,
            content_length=content_length,
        )
    except Exception as e:  # pragma: no cover
        logger.debug(f"metrics mirror failed for {stage}/{outcome}: {e}")
