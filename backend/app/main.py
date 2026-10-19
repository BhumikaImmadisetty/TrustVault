"""
TrustVault FastAPI Application Entry Point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_mongo_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup configuration and clean teardown of database connections.
    """
    yield
    # Clean shutdown of MongoDB client
    await close_mongo_connection()


app = FastAPI(
    title=settings.APP_NAME,
    description="TrustVault: Secure Document-Sharing RESTful API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Mount primary versioned API v1 router
app.include_router(api_router, prefix="/api/v1")

# Also mount auth router at /auth so requests to either /api/v1/auth or /auth succeed
app.include_router(auth_router, prefix="/auth", include_in_schema=False)


@app.get("/health", tags=["Health"], summary="Service Health Check")
async def health_check():
    """Simple non-sensitive service health status check."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }
