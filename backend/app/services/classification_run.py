"""Classification run health: fail backlog runs when model calls mostly error."""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

# Defaults for issue #279.
MODEL_CALL_ERROR_FAIL_RATE_THRESHOLD = 0.9
MODEL_CALL_ERROR_FAIL_MIN_CALLS = 50

# Stable start of str(ClassificationRunModelCallFailure) for GitHub issue dedup
# (github._generate_issue_hash uses error[:100]).
CLASSIFICATION_RUN_FAILURE_ISSUE_PREFIX = (
    "Classification backlog run failed because the model-call error rate exceeded "
    "the configured threshold in process_cities_backlog (systemic LLM or API "
    "failure such as OpenRouter credits, not per-headline content discards). "
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization|api[_-]?key|bearer)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[a-zA-Z0-9]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+\b"),
)


class ClassificationRunModelCallFailure(Exception):
    """Raised when a classification batch/run exceeds the model-call error threshold."""

    def __init__(self, variable_details: str) -> None:
        self.variable_details = variable_details
        super().__init__(CLASSIFICATION_RUN_FAILURE_ISSUE_PREFIX + variable_details)


@dataclass(frozen=True)
class ClassificationRunStats:
    violent_death: int
    discarded: int
    model_call_errors: int
    other_errors: int = 0

    @classmethod
    def from_mapping(cls, data: dict) -> ClassificationRunStats:
        return cls(
            violent_death=int(data.get("violent_death", 0)),
            discarded=int(data.get("discarded", 0)),
            model_call_errors=int(data.get("model_call_errors", 0)),
            other_errors=int(data.get("other_errors", 0)),
        )

    @property
    def model_call_attempts(self) -> int:
        return self.violent_death + self.discarded + self.model_call_errors

    @property
    def model_call_error_rate(self) -> float:
        attempts = self.model_call_attempts
        if attempts == 0:
            return 0.0
        return self.model_call_errors / attempts


def redact_secrets(message: str, max_len: int = 300) -> str:
    text = (message or "").strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def should_fail_classification_run(stats: ClassificationRunStats) -> bool:
    attempts = stats.model_call_attempts
    if attempts < MODEL_CALL_ERROR_FAIL_MIN_CALLS:
        return False
    return stats.model_call_error_rate >= MODEL_CALL_ERROR_FAIL_RATE_THRESHOLD


def format_model_call_failure_details(
    stats: ClassificationRunStats,
    first_error: str | None,
) -> str:
    attempts = stats.model_call_attempts
    rate_pct = stats.model_call_error_rate * 100.0
    snippet = redact_secrets(first_error or "(no error message captured)")
    return (
        f"model_call_errors={stats.model_call_errors} "
        f"model_call_attempts={attempts} error_rate={rate_pct:.1f}% "
        f"first_error={snippet!r}"
    )


def format_model_call_failure_log(
    stats: ClassificationRunStats,
    first_error: str | None,
) -> str:
    return (
        "[CLASSIFICATION_RUN_FAILURE] "
        + format_model_call_failure_details(stats, first_error)
    )


def raise_if_classification_run_failed(
    stats: ClassificationRunStats | dict,
    first_model_call_error: str | None = None,
) -> None:
    """Log and raise when model-call error rate exceeds configured thresholds."""
    if isinstance(stats, dict):
        stats = ClassificationRunStats.from_mapping(stats)
    if not should_fail_classification_run(stats):
        return
    details = format_model_call_failure_details(stats, first_model_call_error)
    logger.error(f"[CLASSIFICATION_RUN_FAILURE] {details}")
    raise ClassificationRunModelCallFailure(details)
