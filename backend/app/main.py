"""
TrustVault FastAPI Application Entry Point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_mongo_connection, get_db, init_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup configuration and clean teardown of database connections.
    """
    # Initialize indexes if MongoDB is available
    try:
        await init_indexes(get_db())
    except Exception:
        pass
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

# Configure CORS strictly for the intended frontend origin (Requirement 6)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
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
