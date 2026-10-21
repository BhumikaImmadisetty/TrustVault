"""
API v1 central router aggregating all v1 endpoint routers.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import audit
from app.api.v1.endpoints import auth
from app.api.v1.endpoints import documents

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(audit.router, prefix="/audit", tags=["Audit Trail"])
