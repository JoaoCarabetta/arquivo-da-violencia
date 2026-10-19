"""FastAPI application factory and main entry point."""

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import PlainTextResponse
from loguru import logger

from app.config import get_settings
from app.database import init_db
from app.llms_txt import LLMS_TXT
from app.public_cors import PublicAPICorsMiddleware
from app.services.worker_monitor import monitor_worker_health
from app.auth import validate_auth_config

OPENAPI_DESCRIPTION = """
Public HTTP API for the Arquivo da Violência — a news-derived homicide archive
for Brazil, **not** official SIM/FBSP statistics.

Claude Desktop: add this OpenAPI URL as a custom connector. No MCP required.
Website ask box and other clients share these same routes.

**When to call which tool**

- Street / “near me” (example: *Rua Umari 28, Rio de Janeiro*):
  `GET /api/public/geocode` then `GET /api/public/nearby`. Read `location_precision`.
- Trend in a UF + subtype (example: *O feminicídio está subindo no Ceará?*):
  `GET /api/public/stats/series?state=CE&subtype=feminicidio&interval=week&days=365`.
- One-shot prose: `POST /api/public/ask` with `{"question": "..."}`.
  The model only picks tools and writes from their JSON — never raw SQL.

Discovery: `/llms.txt` and `/api/openapi.json`.
Always attribute `source` + `methodology_url`.
"""

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    validate_auth_config()
    
    if settings.is_sqlite:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize database (creates tables if not using alembic)
    # await init_db()
    logger.info(f"Database ready: {settings.database_display_name}")

    # Background monitor that alerts (via Telegram) if the ARQ worker goes silent.
    monitor_stop = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_worker_health(monitor_stop))

    yield
    
    # Shutdown
    logger.info("Shutting down application")
    monitor_stop.set()
    try:
        await asyncio.wait_for(monitor_task, timeout=5)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        monitor_task.cancel()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=OPENAPI_DESCRIPTION,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # Locked CORS for admin routes (specific site origins + credentials).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Wildcard CORS for /api/public/*, /api/openapi.json, /llms.txt only.
    app.add_middleware(PublicAPICorsMiddleware)

    @app.get("/llms.txt", include_in_schema=False)
    async def llms_txt() -> PlainTextResponse:
        return PlainTextResponse(LLMS_TXT, media_type="text/plain; charset=utf-8")

    # Health check endpoint (available at both / and /api/ for flexibility)
    @app.get("/health")
    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "version": settings.app_version}

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=settings.app_name,
            version=settings.app_version,
            description=OPENAPI_DESCRIPTION,
            routes=app.routes,
        )
        schema["info"]["x-attribution"] = {
            "source": "Arquivo da Violência",
            "methodology_url": "https://arquivodaviolencia.com.br/metodologia",
        }
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi

    # Import and include routers
    from app.routers import unique_events, source_google_news, raw_events, pipeline, stats, public, auth
    
    # Public routes (no auth required)
    app.include_router(public.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    
    # Admin routes (auth required)
    app.include_router(unique_events.router, prefix=settings.api_prefix)
    app.include_router(source_google_news.router, prefix=settings.api_prefix)
    app.include_router(raw_events.router, prefix=settings.api_prefix)
    app.include_router(pipeline.router, prefix=settings.api_prefix)
    app.include_router(stats.router, prefix=settings.api_prefix)

    if settings.metrics_enabled:
        from prometheus_fastapi_instrumentator import Instrumentator

        from app.metrics import REGISTRY

        Instrumentator(registry=REGISTRY).instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )

    return app


# Create app instance for uvicorn
app = create_app()
