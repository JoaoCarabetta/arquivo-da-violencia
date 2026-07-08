#!/usr/bin/env python3
"""Alertmanager webhook receiver: Telegram for all alerts, Cursor agent for critical."""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("alert-router")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_URL = os.environ.get("PIPELINE_HEALTH_WEBHOOK_URL", "")
WEBHOOK_AUTH = (
    os.environ.get("PIPELINE_HEALTH_WEBHOOK_AUTH", "")
    or os.environ.get("CURSOR_AUTOMATION_TOKEN", "")
).removeprefix("Bearer ").strip()
ROUTER_WEBHOOK_SECRET = os.environ.get("ALERT_ROUTER_WEBHOOK_SECRET", "").strip()
GRAFANA_URL = os.environ.get(
    "GRAFANA_URL", "https://observability.carabetta.xyz"
).rstrip("/")

CRITICAL_ALERT_NAMES = frozenset({
    "WorkerDown",
    "RedisDisconnected",
    "ApiScrapeDown",
    "WorkerScrapeDown",
    "StuckSourcesCritical",
    "QueueDepthCritical",
    "CronIngestStale",
    "HostDiskCritical",
    "HostMemoryCritical",
    "ObservabilityScrapeDown",
})

ALERT_HINTS: dict[str, str] = {
    "WorkerDown": "Check Redis heartbeat key and restart worker: docker compose -p prod restart worker",
    "RedisDisconnected": "Check arquivo-redis container: docker compose -p prod ps redis",
    "ApiScrapeDown": "Check API container and UFW from obs VPS to :8000",
    "WorkerScrapeDown": "Check worker :9091 metrics server and UFW :9091",
    "StuckSourcesCritical": "Run: bash scripts/check-pipeline-health.sh --remediate",
    "StuckSourcesWarning": "Monitor stuck sources; run --remediate if count grows",
    "QueueDepthCritical": "Check ARQ queue and worker logs; consider --remediate",
    "QueueDepthWarning": "Queue building; inspect worker throughput",
    "CronIngestStale": "Check ENABLE_CRON and worker logs for ingest_cities_hourly failures",
    "CronIngestWarning": "Hourly ingest delayed; check worker cron schedule",
    "HostDiskCritical": "Free disk space on affected VPS (docker system prune, logs)",
    "HostDiskWarning": "Disk usage rising; plan cleanup",
    "HostMemoryCritical": "Check memory-heavy containers; consider restart or resize",
    "HostMemoryWarning": "Memory usage elevated",
    "HostCpuWarning": "CPU sustained high load; inspect top processes",
    "ObservabilityScrapeDown": "Check target reachability and UFW rules from obs VPS",
    "ClassificationBacklogWarning": "Classification backlog growing",
    "OpenFailureIssuesWarning": "Review open pipeline-failure GitHub issues",
    "HeartbeatMissesWarning": "Worker heartbeat intermittent; may recover or escalate to WorkerDown",
}


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")[:500]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return exc.code, body
    except urllib.error.URLError as exc:
        log.error("HTTP request failed: %s", exc)
        return 0, str(exc)


def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured; skipping notification")
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    status, body = _post_json(
        url,
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": False,
        },
    )
    if status != 200:
        log.error("Telegram failed: %s %s", status, body)
        return False
    log.info("Telegram sent (%d chars)", len(text))
    return True


def send_cursor_webhook(failures: list[str], warnings: list[str], prompt: str) -> bool:
    if not WEBHOOK_URL:
        log.warning("Cursor webhook not configured; skipping agent dispatch")
        return False
    if not WEBHOOK_AUTH:
        log.error("Cursor webhook auth missing (PIPELINE_HEALTH_WEBHOOK_AUTH)")
        return False
    payload = {
        "status": "unhealthy",
        "failures": failures,
        "warnings": warnings,
        "host": "prod",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt": prompt,
        "source": "prometheus-alertmanager",
    }
    status, body = _post_json(
        WEBHOOK_URL,
        payload,
        headers={"Authorization": f"Bearer {WEBHOOK_AUTH}"},
    )
    if status < 200 or status >= 300:
        log.error("Cursor webhook failed: %s %s", status, body)
        return False
    log.info("Cursor webhook dispatched for %s", failures)
    return True


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_telegram_message(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    alerts = payload.get("alerts") or []
    lines: list[str] = []

    if status == "resolved":
        lines.append("✅ <b>Alerts resolved</b>")
    elif any(a.get("labels", {}).get("severity") == "critical" for a in alerts if a.get("status") == "firing"):
        lines.append("🚨 <b>CRITICAL alerts</b>")
    else:
        lines.append("⚠️ <b>Warning alerts</b>")

    lines.append(f"<i>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>")
    lines.append("")

    for alert in alerts:
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        name = labels.get("alertname", "Unknown")
        severity = labels.get("severity", "?")
        state = alert.get("status", "firing")
        summary = annotations.get("summary", name)
        description = annotations.get("description", "")

        icon = "🔴" if severity == "critical" else "🟡"
        if state == "resolved":
            icon = "✅"
        lines.append(f"{icon} <b>{_escape_html(name)}</b> [{severity}] ({state})")
        lines.append(f"  {_escape_html(summary)}")
        if description and description != summary:
            lines.append(f"  {_escape_html(description)}")
        lines.append("")

    lines.append(f'<a href="{GRAFANA_URL}/d/arquivo-pipeline">Pipeline dashboard</a> · '
                 f'<a href="{GRAFANA_URL}/d/arquivo-hosts">Host dashboard</a>')
    return "\n".join(lines)


def build_agent_prompt(alert_names: list[str]) -> str:
    hints = [f"- {n}: {ALERT_HINTS.get(n, 'Investigate via SSH')}" for n in alert_names]
    return (
        "CRITICAL ALERT from Prometheus Alertmanager.\n\n"
        f"Alerts: {', '.join(alert_names)}\n\n"
        "SSH to hetzner-arv (77.42.72.111), cd /root/arquivo-da-violencia.\n"
        "Run: bash scripts/check-pipeline-health.sh --json\n"
        "Inspect: docker logs arquivo-worker --since 2h | tail -150\n"
        "Inspect: docker logs arquivo-api --since 2h | grep -i error | tail -30\n\n"
        "Suggested actions:\n"
        + "\n".join(hints)
        + "\n\nApply Tier-A remediation if safe (bash scripts/check-pipeline-health.sh --remediate). "
        "For code bugs, branch fix/pipeline-<issue> from develop and open PR. Never push master directly. "
        "Docs: docs/pipeline-auto-remediation.md"
    )


def handle_alertmanager_payload(payload: dict[str, Any]) -> dict[str, Any]:
    alerts = payload.get("alerts") or []
    firing = [a for a in alerts if a.get("status") == "firing"]
    resolved = [a for a in alerts if a.get("status") == "resolved"]

    result: dict[str, Any] = {
        "telegram_sent": False,
        "cursor_dispatched": False,
        "firing_count": len(firing),
        "resolved_count": len(resolved),
    }

    if not alerts:
        return result

    telegram_ok = send_telegram(format_telegram_message(payload))
    result["telegram_sent"] = telegram_ok

    failure_names = list(dict.fromkeys(
        a.get("labels", {}).get("alertname", "")
        for a in firing
        if a.get("labels", {}).get("alertname") in CRITICAL_ALERT_NAMES
        and a.get("labels", {}).get("agent") == "true"
    ))
    warning_names = list(dict.fromkeys(
        a.get("labels", {}).get("alertname", "Unknown")
        for a in firing
        if a.get("labels", {}).get("severity") == "warning"
    ))

    if failure_names and payload.get("status") != "resolved":
        prompt = build_agent_prompt(failure_names)
        result["cursor_dispatched"] = send_cursor_webhook(
            failures=failure_names,
            warnings=warning_names,
            prompt=prompt,
        )

    result["ok"] = telegram_ok and (
        not failure_names or payload.get("status") == "resolved" or result["cursor_dispatched"]
    )
    return result


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not ROUTER_WEBHOOK_SECRET:
        log.error("ALERT_ROUTER_WEBHOOK_SECRET not set — rejecting webhook")
        return False
    auth = handler.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    return token == ROUTER_WEBHOOK_SECRET


class AlertHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        if self.path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"status": "ok", "telegram": bool(TELEGRAM_BOT_TOKEN)}).encode()
            )
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path not in ("/alerts", "/"):
            self.send_response(404)
            self.end_headers()
            return

        if not _authorized(self):
            self.send_response(401)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        log.info(
            "Received Alertmanager webhook: status=%s alerts=%d",
            payload.get("status"),
            len(payload.get("alerts") or []),
        )
        result = handle_alertmanager_payload(payload)
        status_code = 200 if result.get("ok", True) else 503

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), AlertHandler)
    log.info("alert-router listening on :%d", port)
    log.info(
        "Telegram=%s Cursor=%s RouterAuth=%s Grafana=%s",
        "configured" if TELEGRAM_BOT_TOKEN else "disabled",
        "configured" if WEBHOOK_URL else "disabled",
        "configured" if ROUTER_WEBHOOK_SECRET else "MISSING",
        GRAFANA_URL,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
