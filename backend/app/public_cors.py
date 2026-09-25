"""Wildcard CORS for public read/ask routes only.

Admin routes keep the locked origin list from CORSMiddleware.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

PUBLIC_CORS_PATHS = (
    "/api/public",
    "/api/openapi.json",
    "/llms.txt",
)

PUBLIC_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "86400",
}


def is_public_cors_path(path: str) -> bool:
    return path == "/llms.txt" or path.startswith("/api/public") or path == "/api/openapi.json"


class PublicAPICorsMiddleware(BaseHTTPMiddleware):
    """Allow any Origin on /api/public/*, /api/openapi.json, and /llms.txt."""

    async def dispatch(self, request: Request, call_next):
        if not is_public_cors_path(request.url.path):
            return await call_next(request)

        if request.method == "OPTIONS":
            return Response(status_code=204, headers=dict(PUBLIC_CORS_HEADERS))

        response = await call_next(request)
        for key, value in PUBLIC_CORS_HEADERS.items():
            if key == "Access-Control-Max-Age":
                continue
            response.headers[key] = value
        return response
