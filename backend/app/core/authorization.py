"""
Central authorization helpers for TrustVault documents.

Enforces document access policies based on live MongoDB records.
Access rules:
- Document must exist and not be soft-deleted (status != 'deleted').
- Owner access: current_user.id == document.owner_id.
- Read access: owner access OR an active permission grant with level 'read' or 'edit'.
- Edit access: owner access OR an active permission grant with level 'edit'.
- Administrators do NOT automatically bypass private-document permissions.
- Permissions are always checked against live database state (never cached).
"""

from typing import Any
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from app.models.user import UserResponse


async def get_active_document(
    document_id: str,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    """
    Retrieve an active (non-deleted) document by ID.
    Raises 404 if the document does not exist or has been soft-deleted.
    Fails safely on database outages with 503.
    """
    try:
        doc = await db["documents"].find_one({
            "$or": [{"id": document_id}, {"_id": document_id}],
            "status": {"$ne": "deleted"},
        })
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return doc


async def verify_document_owner(
    document_id: str,
    current_user: UserResponse,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    """
    Verify that the current user is the owner of the document.

    Security guarantees:
    - Never accepts owner_id from request body/headers.
    - Resolves document from database.
    - Strict check: document['owner_id'] == current_user.id.
    - Administrators do not automatically bypass ownership.
    - Returns document dict on success, raises 403 or 404 on failure.
    """
    doc = await get_active_document(document_id, db)
    if doc.get("owner_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only the document owner can perform this operation.",
        )
    return doc


async def verify_document_read_access(
    document_id: str,
    current_user: UserResponse,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    """
    Verify that the current user has read access to the document.

    Access granted if:
    1. current_user is the document owner, OR
    2. current_user has an active permission grant with level 'read' or 'edit'.

    Evaluates live database state to ensure permission revocations take immediate effect.
    Administrators do not bypass permission checks for private documents.
    """
    doc = await get_active_document(document_id, db)

    # 1. Document owner always has read access
    if doc.get("owner_id") == current_user.id:
        return doc

    # 2. Check for active permission grant in MongoDB
    actual_doc_id = str(doc.get("id") or doc.get("_id"))
    try:
        perm = await db["permissions"].find_one({
            "document_id": actual_doc_id,
            "grantee_id": current_user.id,
        })
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if perm and perm.get("permission_level") in ("read", "edit"):
        return doc

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: You do not have permission to view this document.",
    )


async def verify_document_edit_access(
    document_id: str,
    current_user: UserResponse,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    """
    Verify that the current user has edit access to the document.

    Access granted if:
    1. current_user is the document owner, OR
    2. current_user has an active permission grant with level 'edit'.

    Evaluates live database state to ensure permission revocations take immediate effect.
    Administrators do not bypass permission checks for private documents.
    """
    doc = await get_active_document(document_id, db)

    # 1. Document owner always has edit access
    if doc.get("owner_id") == current_user.id:
        return doc

    # 2. Check for active permission grant with 'edit' level
    actual_doc_id = str(doc.get("id") or doc.get("_id"))
    try:
        perm = await db["permissions"].find_one({
            "document_id": actual_doc_id,
            "grantee_id": current_user.id,
        })
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if perm and perm.get("permission_level") == "edit":
        return doc

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: You do not have permission to edit this document.",
    )
