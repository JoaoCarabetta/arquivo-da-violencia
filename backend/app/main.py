"""FastAPI application factory and main entry point."""

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import get_settings
from app.database import init_db
from app.services.worker_monitor import monitor_worker_health
from app.auth import validate_auth_config

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
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint (available at both / and /api/ for flexibility)
    @app.get("/health")
    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "version": settings.app_version}

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

        Instrumentator().instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )

    return app


# Create app instance for uvicorn
app = create_app()
