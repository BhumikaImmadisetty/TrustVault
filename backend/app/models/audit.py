"""
Audit trail models for TrustVault.
Defines schemas for audit event recording, database representation,
and administrative audit trail querying.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field


class AuditAction(str, Enum):
    """
    Standardized audit actions across TrustVault.
    """
    LOGIN = "auth.login"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_DOWNLOAD = "document.download"
    DOCUMENT_UPDATE = "document.update"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_ACCESS = "document.access"
    PERMISSION_GRANT = "permission.grant"
    PERMISSION_REVOKE = "permission.revoke"


class AuditOutcome(str, Enum):
    """
    Outcome of the audited action: success or denied.
    """
    SUCCESS = "success"
    DENIED = "denied"


class AuditLogInDB(BaseModel):
    """
    Internal audit log document stored in MongoDB 'audit_logs' collection.
    Strictly excludes passwords, hashes, JWTs, authorization headers,
    document contents, and filesystem paths.
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique audit event identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the event occurred",
    )
    actor_id: Optional[str] = Field(default=None, description="User ID of the actor when known")
    action: str = Field(description="Action identifier (e.g. auth.login, document.download)")
    document_id: Optional[str] = Field(default=None, description="Target document ID when applicable")
    outcome: str = Field(description="Action outcome ('success' or 'denied')")
    status_code: Optional[int] = Field(default=None, description="HTTP status code associated with the outcome")
    reason: Optional[str] = Field(default=None, max_length=200, description="Safe summary reason or error code")
    correlation_id: Optional[str] = Field(default=None, max_length=128, description="Request correlation identifier")

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    """
    Public administrative representation of an audit event.
    Strictly excludes secrets, credentials, tokens, document content, and file paths.
    """
    id: str = Field(description="Unique audit event identifier")
    timestamp: datetime = Field(description="UTC timestamp")
    actor_id: Optional[str] = Field(default=None, description="Actor user ID when known")
    action: str = Field(description="Action performed")
    document_id: Optional[str] = Field(default=None, description="Target document ID when applicable")
    outcome: str = Field(description="Outcome ('success' or 'denied')")
    status_code: Optional[int] = Field(default=None, description="HTTP status code")
    reason: Optional[str] = Field(default=None, description="Safe reason or error descriptor")
    correlation_id: Optional[str] = Field(default=None, description="Request correlation ID")

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class AuditLogListResponse(BaseModel):
    """Paginated list of audit events for administrator inspection."""
    events: list[AuditLogResponse] = Field(description="List of audit log records")
    total: int = Field(ge=0, description="Total matching audit records")
    skip: int = Field(ge=0, description="Number of skipped records")
    limit: int = Field(ge=1, description="Page size limit")
