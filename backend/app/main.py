"""FastAPI application factory and main entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import get_settings
from app.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    
    # Ensure instance directory exists
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize database (creates tables if not using alembic)
    # await init_db()
    logger.info(f"Database ready: {settings.database_path}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")


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

    # Health check endpoint
    @app.get("/health")
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

    return app


# Create app instance for uvicorn
app = create_app()
# deploy test 1766336133
