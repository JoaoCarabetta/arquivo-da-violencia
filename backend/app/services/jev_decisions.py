"""OpenRouter Decisions API client for TypeSafe Jev (System One).

Jev is not a chat model. Official call path:

    POST https://openrouter.ai/api/alpha/decisions
    Authorization: Bearer $OPENROUTER_API_KEY

Request: ``{model, state, questions}``. Response: ``{answers, usage, model}``.
See https://openrouter.ai/docs/guides/community/jev
"""

from __future__ import annotations

import json
from typing import Any

import httpx

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL_PINNED = "typesafe/jev-1.13"
JEV_MODEL_ALIAS = "~typesafe/jev-latest"


class JevDecisionsError(Exception):
    """Decisions API transport or response error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def is_jev_model(model: str | None) -> bool:
    """True for OpenRouter / TypeSafe Jev slugs (pinned, alias, or bare)."""
    if not model:
        return False
    slug = model.strip().lower().lstrip("~")
    return slug.startswith("typesafe/jev") or slug.startswith("jev-") or slug == "jev-latest"


def normalize_jev_model(model: str) -> str:
    """Map bare TypeSafe IDs onto the OpenRouter Decisions model field."""
    slug = model.strip()
    if slug.startswith("~"):
        return slug
    lower = slug.lower()
    if lower.startswith("typesafe/jev"):
        return slug
    if lower == "jev-latest":
        return JEV_MODEL_ALIAS
    if lower.startswith("jev-"):
        return f"typesafe/{slug}"
    return slug


def _is_in_flight_budget_error(body: str) -> bool:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return False
    metadata = error.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return metadata.get("limit_source") == "openrouter_in_flight_budget"


def submit_decisions(
    *,
    model: str,
    state: Any,
    questions: dict[str, Any],
    api_key: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST one Decisions request. Raises ``JevDecisionsError`` on failure."""
    payload = {
        "model": normalize_jev_model(model),
        "state": state,
        "questions": questions,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://arquivodaviolencia.com.br",
        "X-OpenRouter-Title": "Arquivo da Violencia",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(DECISIONS_URL, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise JevDecisionsError(
            f"Decisions request failed: {exc}",
            retryable=True,
        ) from exc

    if not response.is_success:
        retryable = (
            response.status_code == 429
            or response.status_code >= 500
            or (response.status_code == 402 and _is_in_flight_budget_error(response.text))
        )
        raise JevDecisionsError(
            f"Decisions {response.status_code}: {response.text}",
            status_code=response.status_code,
            retryable=retryable,
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise JevDecisionsError("Decisions response is not JSON") from exc
    if not isinstance(data, dict) or "answers" not in data:
        raise JevDecisionsError("Decisions response missing answers")
    if not isinstance(data["answers"], dict):
        raise JevDecisionsError("Decisions answers must be an object")
    return data
