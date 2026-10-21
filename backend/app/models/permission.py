"""
Document permission models for TrustVault.
Defines Pydantic schemas for access control grants, queries, and responses.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PermissionLevel(str, Enum):
    """
    Access permission level granted on a document.
    - read: Allows reading/viewing document metadata and content.
    - edit: Allows reading and editing/updating document content and metadata.
    """
    READ = "read"
    EDIT = "edit"


class PermissionInDB(BaseModel):
    """
    Internal document permission schema stored in MongoDB 'permissions' collection.
    Enforces access control between document owners and grantees.
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique permission grant identifier")
    document_id: str = Field(description="Unique identifier of the target document")
    owner_id: str = Field(description="User ID of the document owner")
    grantee_id: str = Field(description="User ID of the recipient user granted access")
    grantee_email: Optional[str] = Field(default=None, description="Email of the grantee for display purposes")
    permission_level: PermissionLevel = Field(description="Granted permission level ('read' or 'edit')")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when permission was granted (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when permission was last updated (UTC)",
    )

    model_config = ConfigDict(from_attributes=True)


class PermissionGrantRequest(BaseModel):
    """
    Request body for granting document access to another registered user.
    Owner must provide either grantee_id or grantee_email.
    owner_id is NEVER accepted from the request body.
    """
    grantee_id: Optional[str] = Field(default=None, description="User ID of the recipient user")
    grantee_email: Optional[str] = Field(default=None, description="Email address of the recipient user")
    permission_level: PermissionLevel = Field(description="Permission level to grant: 'read' or 'edit'")

    @field_validator("permission_level", mode="before")
    @classmethod
    def normalize_permission_level(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    model_config = ConfigDict(extra="ignore")


class PermissionResponse(BaseModel):
    """
    Public permission representation returned by API endpoints.
    Strictly excludes server-internal fields, storage paths, passwords, and tokens.
    """
    id: str = Field(description="Unique permission grant identifier")
    document_id: str = Field(description="Document ID")
    owner_id: str = Field(description="Owner user ID")
    grantee_id: str = Field(description="Grantee user ID")
    grantee_email: Optional[str] = Field(default=None, description="Grantee email address")
    permission_level: PermissionLevel = Field(description="Permission level ('read' or 'edit')")
    created_at: datetime = Field(description="Grant timestamp (UTC)")
    updated_at: datetime = Field(description="Last update timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class PermissionListResponse(BaseModel):
    """Paginated or listed response containing permission grants for a document."""
    permissions: list[PermissionResponse] = Field(description="List of active permission grants")
    total: int = Field(ge=0, description="Total number of active permission grants")
