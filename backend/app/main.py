"""
TrustVault FastAPI Application Entry Point.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import (
    check_db_connection,
    close_mongo_connection,
    get_db,
    init_indexes,
)

logger = logging.getLogger("trustvault.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup configuration and clean teardown of database connections.
    """
    # Attempt index initialization; log sanitized error on failure without silently swallowing
    try:
        await init_indexes(get_db())
    except Exception as exc:
        logger.error(
            "Essential database index initialization failed during application startup: %s",
            exc.__class__.__name__,
        )
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

# Configure CORS strictly for configured frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Mount primary versioned API v1 router
app.include_router(api_router, prefix="/api/v1")

# Also mount auth router at /auth so requests to either /api/v1/auth or /auth succeed
app.include_router(auth_router, prefix="/auth", include_in_schema=False)


@app.get(
    "/health",
    tags=["Health"],
    summary="Service and Database Health Check",
    response_description="Sanitized service and database availability status",
    responses={
        200: {
            "description": "Service and database connection are healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "database": "connected",
                        "app": "TrustVault",
                        "env": "development",
                    }
                }
            },
        },
        503: {
            "description": "Database connection is unavailable or degraded",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "database": "disconnected",
                        "app": "TrustVault",
                        "env": "development",
                    }
                }
            },
        },
    },
)
async def health_check(response: Response):
    """
    Service health status check verifying application and MongoDB connectivity.

    Returns HTTP 200 when the service and MongoDB ping are healthy.
    Returns HTTP 503 when MongoDB is unreachable or returns an unhealthy ping.
    Never exposes credentials, connection URIs, internal paths, or stack traces.
    """
    try:
        is_db_healthy = await check_db_connection()
    except Exception as exc:
        logger.error("Health check database probe failed: %s", exc.__class__.__name__)
        is_db_healthy = False

    if not is_db_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
        }

    response.status_code = status.HTTP_200_OK
    return {
        "status": "healthy",
        "database": "connected",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }
