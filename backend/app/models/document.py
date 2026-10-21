"""
Document metadata models for TrustVault.
Defines Pydantic schemas for document creation, storage records,
and public API responses. File content is never embedded in these schemas.
"""

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentStatus(str, Enum):
    """
    Lifecycle status of a document stored in TrustVault.
    - active:   Document is accessible to authorised users.
    - archived: Document is retained but hidden from default listings.
    - deleted:  Soft-deleted; file and metadata are pending permanent removal.
    """
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class DocumentInDB(BaseModel):
    """
    Internal document schema reflecting the MongoDB document structure.
    Stores file metadata, storage path, and ownership information.
    The 'storage_path' field is server-controlled and never exposed publicly.
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique document identifier")
    filename: str = Field(description="Original filename supplied by the uploading client")
    content_type: str = Field(description="MIME type of the uploaded file")
    size_bytes: int = Field(ge=0, description="File size in bytes")
    owner_id: str = Field(description="User ID of the document owner (uploader)")
    storage_path: str = Field(description="Server-side absolute path to the stored file (never exposed in API)")
    status: DocumentStatus = Field(default=DocumentStatus.ACTIVE, description="Document lifecycle status")
    description: Optional[str] = Field(default=None, max_length=500, description="Optional document description")
    category: Optional[str] = Field(default=None, max_length=100, description="Optional document category")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the document was first uploaded (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the most recent metadata update (UTC)",
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    """
    Public document representation returned by API endpoints.
    Strictly excludes storage_path and any server-internal fields.
    """
    id: str = Field(description="Unique document identifier")
    filename: str = Field(description="Original filename")
    content_type: str = Field(description="MIME type")
    size_bytes: int = Field(description="File size in bytes")
    owner_id: str = Field(description="User ID of the document owner")
    status: DocumentStatus = Field(description="Document lifecycle status")
    description: Optional[str] = Field(default=None, description="Optional document description")
    category: Optional[str] = Field(default=None, description="Optional document category")
    created_at: datetime = Field(description="Upload timestamp (UTC)")
    updated_at: Optional[datetime] = Field(default=None, description="Timestamp of the most recent metadata update (UTC)")

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class DocumentUpdateRequest(BaseModel):
    """
    Request schema for updating document metadata.
    Allows updating filename, description, or category.
    Strictly forbids client modification of owner_id, storage_path,
    id, status, content_type, or size_bytes.
    """
    filename: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated original filename",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Updated document description",
    )
    category: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Document category or classification tag",
    )

    @field_validator("filename", mode="before")
    @classmethod
    def validate_filename(cls, v: object) -> object:
        if v is not None:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("Filename must not be empty or whitespace only.")
            cleaned = os.path.basename(v.strip())
            if not cleaned or cleaned in (".", ".."):
                raise ValueError("Invalid filename.")
            return cleaned
        return v

    @field_validator("description", "category", mode="before")
    @classmethod
    def strip_strings(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    model_config = ConfigDict(extra="forbid")


class DocumentListResponse(BaseModel):
    """Paginated list of documents owned by the authenticated user."""
    documents: list[DocumentResponse] = Field(description="List of document records")
    total: int = Field(ge=0, description="Total number of documents matching the query")


# Re-export permission models for convenient access
from app.models.permission import (  # noqa: E402
    PermissionGrantRequest,
    PermissionInDB,
    PermissionLevel,
    PermissionListResponse,
    PermissionResponse,
)
