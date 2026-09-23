"""Thin Prefect trigger for Arquivo news pipeline (trilha B cutover).

Used by ``/api/pipeline/*`` and health remediates when
``PIPELINE_ORCHESTRATOR=prefect``. Talks to Prefect Server HTTP API —
no ARQ Redis enqueue.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

# Map legacy ARQ task names → Prefect deployment names (flow_name/deployment_name).
DEPLOYMENT_BY_TASK: dict[str, str] = {
    "ingest_cities_task": "arquivo_ingest_cities/arquivo-ingest-prod",
    "ingest_cities_hourly": "arquivo_ingest_cities/arquivo-ingest-prod",
    "ingest_cities_full_pipeline": "arquivo_full_pipeline/arquivo-full-pipeline-prod",
    "process_cities_backlog": "arquivo_process_backlog/arquivo-process-backlog-prod",
    "classify_pending_task": "arquivo_process_backlog/arquivo-process-backlog-prod",
    # Stage-only remediates: run backlog (covers classify→geocode). Clear mapping.
    "download_classified_task": "arquivo_process_backlog/arquivo-process-backlog-prod",
    "extract_ready_task": "arquivo_process_backlog/arquivo-process-backlog-prod",
    "batch_dedup_task": "arquivo_process_backlog/arquivo-process-backlog-prod",
    "batch_enrich_task": "arquivo_process_backlog/arquivo-process-backlog-prod",
    "batch_geocode_task": "arquivo_process_backlog/arquivo-process-backlog-prod",
}

# Ambiguous / costly single-source jobs — callers should alert-only, not auto-run.
AMBIGUOUS_TASKS = frozenset(
    {
        "classify_task",
        "download_task",
        "extract_task",
        "enrich_task",
        "run_full_pipeline",
        "ingest_task",
    }
)


def orchestrator() -> str:
    return (os.environ.get("PIPELINE_ORCHESTRATOR") or "arq").strip().lower()


def using_prefect() -> bool:
    return orchestrator() == "prefect"


def prefect_api_url() -> str:
    return (
        os.environ.get("PREFECT_API_URL")
        or "http://prefect-server:4200/api"
    ).rstrip("/")


def resolve_deployment_name(task: str) -> str | None:
    if task in AMBIGUOUS_TASKS:
        return None
    return DEPLOYMENT_BY_TASK.get(task)


async def _find_deployment_id(client: httpx.AsyncClient, name: str) -> str:
    """Resolve ``flow_name/deployment_name`` to a deployment UUID."""
    if "/" not in name:
        raise ValueError(f"deployment name must be flow/name, got {name!r}")
    flow_name, dep_name = name.split("/", 1)
    # Prefect 3 filter API
    resp = await client.post(
        f"{prefect_api_url()}/deployments/filter",
        json={
            "deployments": {"name": {"any_": [dep_name]}},
            "flows": {"name": {"any_": [flow_name]}},
            "limit": 5,
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        raise RuntimeError(f"Prefect deployment not found: {name}")
    return rows[0]["id"]


async def create_flow_run(
    deployment: str,
    *,
    parameters: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a flow run for a named deployment (``flow/deployment``).

    Returns ``{job_id, deployment, status, orchestrator}``.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        dep_id = await _find_deployment_id(client, deployment)
        body: dict[str, Any] = {}
        if parameters:
            body["parameters"] = parameters
        if tags:
            body["tags"] = tags
        resp = await client.post(
            f"{prefect_api_url()}/deployments/{dep_id}/create_flow_run",
            json=body,
        )
        resp.raise_for_status()
        run = resp.json()
        job_id = run.get("id") or run.get("name")
        logger.info(
            f"[PREFECT] created flow_run id={job_id} deployment={deployment}"
        )
        return {
            "status": "queued",
            "job_id": str(job_id),
            "deployment": deployment,
            "orchestrator": "prefect",
            "flow_run_name": run.get("name"),
        }


async def trigger_task(
    task: str,
    *,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map an ARQ task name to a Prefect deployment run (clear cases only)."""
    deployment = resolve_deployment_name(task)
    if not deployment:
        raise ValueError(
            f"Task {task!r} is ambiguous or unmapped for Prefect auto-trigger "
            "(alert-only — use UI or a clear deployment)."
        )
    result = await create_flow_run(
        deployment,
        parameters=parameters,
        tags=["arquivo", "api-trigger", task],
    )
    result["task"] = task
    return result
