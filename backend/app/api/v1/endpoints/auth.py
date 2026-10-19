"""
Authentication API endpoints for TrustVault.
Provides user registration and login functionality.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from app.api.deps import get_current_user, get_database
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import (
    TokenResponse,
    UserInDB,
    UserLogin,
    UserRegister,
    UserResponse,
    UserRole,
)

logger = logging.getLogger("trustvault.api.auth")

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description="Registers a new user with least-privileged role (viewer). Rejects duplicate emails and admin role assignment.",
)
async def register(
    user_in: UserRegister,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserResponse:
    """
    Register a new user account.

    Security guarantees:
    - Normalizes email to lowercase and strips whitespace.
    - Prevents public self-assignment of the admin or owner roles (forces VIEWER).
    - Hashes password using Argon2id before database insertion.
    - Checks for existing accounts to safely reject duplicates (409 Conflict).
    - Returns public UserResponse which strictly excludes the password hash.
    """
    normalized_email = user_in.email.strip().lower()

    try:
        # Check if an account already exists with this email address
        existing_user = await db["users"].find_one({"email": normalized_email})
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        # Defense-in-depth: regardless of client input, public registration assigns VIEWER
        assigned_role = UserRole.VIEWER

        # Generate salted Argon2id password hash
        hashed_pwd = hash_password(user_in.password)

        # Build internal user database document
        new_user = UserInDB(
            email=normalized_email,
            full_name=user_in.full_name.strip(),
            role=assigned_role,
            is_active=True,
            hashed_password=hashed_pwd,
        )

        user_document = new_user.model_dump()
        user_document["_id"] = new_user.id

        await db["users"].insert_one(user_document)
        logger.info("Successfully registered new user account with ID: %s", new_user.id)

        # Return public user representation (excludes password hash)
        return UserResponse(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
        )

    except HTTPException:
        # Re-raise explicit HTTP exceptions (e.g. 409 Conflict)
        raise
    except PyMongoError as exc:
        logger.error("Database driver error during user registration: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None
    except ValueError as exc:
        # Handles validation errors from security functions safely
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain JWT access token",
    description="Validates user credentials against stored Argon2 hash and returns a signed JWT access token.",
)
async def login(
    credentials: UserLogin,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TokenResponse:
    """
    Authenticate user and issue a JWT access token.

    Security guarantees:
    - Verifies password against stored Argon2id hash using constant-time comparison.
    - Returns a generic 401 error message for both non-existent emails and wrong passwords
      to eliminate user enumeration vectors.
    - Rejects deactivated user accounts.
    - Does not log passwords or tokens.
    """
    normalized_email = credentials.email.strip().lower()
    generic_auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        user_doc = await db["users"].find_one({"email": normalized_email})
        if user_doc is None:
            # Email not found: return generic error to prevent enumeration
            raise generic_auth_error

        stored_hash = user_doc.get("hashed_password")
        if not stored_hash or not isinstance(stored_hash, str):
            raise generic_auth_error

        # Verify candidate password against Argon2 hash
        if not verify_password(credentials.password, stored_hash):
            # Password mismatch: return identical generic error
            raise generic_auth_error

        # Ensure account is active
        if not user_doc.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated. Please contact an administrator.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = str(user_doc.get("id") or user_doc.get("_id"))

        # Issue JWT access token with user_id as subject
        token = create_access_token(subject=user_id)
        logger.info("User ID %s authenticated successfully.", user_id)

        user_response = UserResponse(
            id=user_id,
            email=user_doc["email"],
            full_name=user_doc["full_name"],
            role=UserRole(user_doc["role"]),
            is_active=user_doc.get("is_active", True),
            created_at=user_doc["created_at"],
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=user_response,
        )

    except HTTPException:
        raise
    except PyMongoError as exc:
        logger.error("Database driver error during user login: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
    description="Returns the profile and role of the currently authenticated user based on live database state.",
)
async def get_me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Return the profile of the verified active user."""
    return current_user

