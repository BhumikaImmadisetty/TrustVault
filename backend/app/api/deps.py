"""
FastAPI dependency injection providers for database and authentication.
Implements secure extraction and live database verification of authenticated users.
"""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from app.core.database import get_db
from app.core.security import (
    InvalidTokenError,
    TokenExpiredError,
    decode_access_token,
)
from app.models.user import UserResponse, UserRole

logger = logging.getLogger("trustvault.api.deps")

# auto_error=False allows custom inspection of the Authorization header
http_bearer = HTTPBearer(auto_error=False)


async def get_database() -> AsyncIOMotorDatabase:
    """
    Dependency provider yielding the active MongoDB database instance.
    Enables clean dependency overriding in automated tests.
    """
    return get_db()


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserResponse:
    """
    Extract, verify, and resolve the currently authenticated user.

    Security guarantees:
    1. Rejects missing Authorization header with 401 Unauthorized.
    2. Rejects non-Bearer schemes or empty tokens with 401 Unauthorized.
    3. Validates token signature, expiration (exp), and subject (sub).
    4. Looks up the current user in MongoDB using the verified token subject.
    5. Rejects tokens for nonexistent or deactivated user accounts.
    6. Requirement 8: Reads the current role and account status directly from the
       database rather than trusting any role claim inside the token payload.
    7. Never returns password hashes or logs tokens.
    8. Fails safely on database outages with 503 Service Unavailable.
    """
    unauthorized_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    auth_header = request.headers.get("Authorization")

    # 1. Reject missing Authorization header
    if not auth_header or not auth_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Inspect scheme and extract token string
    scheme, _, param = auth_header.strip().partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme; Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = param.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token missing or empty",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Decode and verify token signature and claims
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise unauthorized_exception

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        raise unauthorized_exception

    # 4. Retrieve live user state from database
    try:
        user_doc = await db["users"].find_one({
            "$or": [{"id": user_id.strip()}, {"_id": user_id.strip()}]
        })
    except PyMongoError as exc:
        logger.error("Database error in get_current_user: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    # 5. Reject nonexistent users
    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account does not exist or has been removed",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 6. Reject deactivated accounts
    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 7. Construct UserResponse from live database state (never trusting token role claims)
    resolved_id = str(user_doc.get("id") or user_doc.get("_id"))
    db_role_str = str(user_doc.get("role", UserRole.VIEWER.value)).lower()

    try:
        live_role = UserRole(db_role_str)
    except ValueError:
        live_role = UserRole.VIEWER

    return UserResponse(
        id=resolved_id,
        email=user_doc["email"],
        full_name=user_doc["full_name"],
        role=live_role,
        is_active=user_doc.get("is_active", True),
        created_at=user_doc["created_at"],
    )


async def require_admin_user(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """
    Dependency ensuring the authenticated user has administrator privileges.
    Evaluates live role from the database. Rejects non-admin users with 403.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Administrator privileges required.",
        )
    return current_user
