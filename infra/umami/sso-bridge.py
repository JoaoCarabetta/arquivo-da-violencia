#!/usr/bin/env python3
"""Mint Umami JWT for Cloudflare Access–authenticated browsers.

Listens on 127.0.0.1:3012. nginx proxies /api/sso-bridge here and the
/login page stores the token in localStorage (umami.auth). Tracker paths
stay public via Cloudflare Access bypass apps.
"""
from __future__ import annotations

import json
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ALLOWED = {"joao@carabetta.xyz", "joao.carabetta@gmail.com"}
UMAMI = "http://127.0.0.1:3001"
ENV = Path("/opt/arquivo-umami/.env")

_cache: dict = {"token": None, "exp": 0}


def load_pw() -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith("UMAMI_ADMIN_PASSWORD="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("UMAMI_ADMIN_PASSWORD missing")


def mint_token() -> str:
    now = time.time()
    if _cache["token"] and now < _cache["exp"]:
        return _cache["token"]
    pw = load_pw()
    req = urllib.request.Request(
        UMAMI + "/api/auth/login",
        data=json.dumps({"username": "admin", "password": pw}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        body = json.load(r)
    token = body["token"]
    _cache["token"] = token
    _cache["exp"] = now + 6 * 3600
    return token


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/token":
            self._json(404, {"error": "not_found"})
            return
        email = (self.headers.get("Cf-Access-Authenticated-User-Email") or "").strip().lower()
        if email not in ALLOWED:
            self._json(401, {"error": "access_required", "email": email})
            return
        try:
            self._json(200, {"token": mint_token()})
        except Exception as e:  # noqa: BLE001 — surface mint errors to caller
            self._json(500, {"error": "mint_failed", "detail": str(e)})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 3012), Handler).serve_forever()
