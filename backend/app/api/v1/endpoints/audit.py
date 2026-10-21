"""
Audit trail inspection endpoints for TrustVault administrators.
Provides paginated, filtered access to recorded audit events.
"""

import logging
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from app.api.deps import get_database, require_admin_user
from app.models.audit import AuditLogListResponse, AuditLogResponse
from app.models.user import UserResponse

logger = logging.getLogger("trustvault.api.audit")

router = APIRouter()


@router.get(
    "/",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="List audit events",
    description=(
        "Retrieve paginated audit trail events with optional filtering by action, outcome, actor, document, and date range. "
        "Strictly restricted to users with the administrator role. "
        "Excludes passwords, credentials, tokens, document content, and server file paths."
    ),
)
async def list_audit_events(
    skip: int = Query(default=0, ge=0, description="Number of audit records to skip for pagination"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of audit records to return"),
    action: Optional[str] = Query(default=None, description="Filter by action name (e.g., auth.login, document.download)"),
    outcome: Optional[str] = Query(default=None, description="Filter by outcome ('success' or 'denied')"),
    actor_id: Optional[str] = Query(default=None, description="Filter by actor user ID"),
    document_id: Optional[str] = Query(default=None, description="Filter by target document ID"),
    start_date: Optional[datetime] = Query(default=None, description="Filter events on or after UTC datetime"),
    end_date: Optional[datetime] = Query(default=None, description="Filter events on or before UTC datetime"),
    current_admin: UserResponse = Depends(require_admin_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> AuditLogListResponse:
    """
    List and filter audit trail logs.

    Security guarantees:
    - Enforces administrator role check via require_admin_user dependency (403 for non-admins).
    - Unauthenticated requests are rejected with 401.
    - Query filters are sanitized and typed to prevent injection attacks.
    - Strictly excludes passwords, hashes, JWTs, authorization headers, contents, and storage paths.
    - Handles database outages safely with 503 Service Unavailable.
    """
    query: dict[str, Any] = {}

    if action:
        query["action"] = action.strip()
    if outcome:
        query["outcome"] = outcome.strip().lower()
    if actor_id:
        query["actor_id"] = actor_id.strip()
    if document_id:
        query["document_id"] = document_id.strip()

    if start_date or end_date:
        date_filter: dict[str, Any] = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date
        query["timestamp"] = date_filter

    try:
        total = await db["audit_logs"].count_documents(query)
        cursor = db["audit_logs"].find(query).sort("timestamp", -1).skip(skip).limit(limit)
        events_raw = await cursor.to_list(length=limit)
    except PyMongoError as exc:
        logger.error(
            "Database error while querying audit logs for admin %s: %s",
            current_admin.id,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    events = [
        AuditLogResponse(
            id=str(e.get("id") or e.get("_id")),
            timestamp=e["timestamp"],
            actor_id=e.get("actor_id"),
            action=e["action"],
            document_id=e.get("document_id"),
            outcome=e["outcome"],
            status_code=e.get("status_code"),
            reason=e.get("reason"),
            correlation_id=e.get("correlation_id"),
        )
        for e in events_raw
    ]

    return AuditLogListResponse(
        events=events,
        total=total,
        skip=skip,
        limit=limit,
    )
