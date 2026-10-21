"""
Core audit trail logging helpers for TrustVault.
Provides fail-safe recording of security and data access events into MongoDB.

Security guarantees:
- Always sanitizes fields to never record passwords, hashes, tokens,
  authorization headers, document contents, or internal storage paths.
- Audit logging errors are trapped and logged safely so failures in audit
  recording never compromise application availability or leak secrets.
- Extracts request correlation IDs from headers (X-Correlation-ID / X-Request-ID).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.audit import AuditAction, AuditOutcome

import re

logger = logging.getLogger("trustvault.audit")

# Patterns matching sensitive data: JWTs, Bearer tokens, credentials, and filesystem paths
_SENSITIVE_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
    re.compile(r"(?:password|pwd|secret|token|hash)\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:/[a-zA-Z0-9_\-.]+){2,}"),
    re.compile(r"(?:[a-zA-Z]:\\[a-zA-Z0-9_\-\\.]+)"),
]


def _sanitize_field(text: Optional[str], max_len: int = 200) -> Optional[str]:
    """Sanitize strings by redacting secrets, paths, and bounding length."""
    if text is None:
        return None
    cleaned = str(text).strip()
    for pattern in _SENSITIVE_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned[:max_len]


def extract_correlation_id(request: Optional[Request]) -> Optional[str]:
    """
    Safely extract a correlation ID from standard request headers.
    Checks X-Correlation-ID and X-Request-ID. Bounded to 128 characters.
    """
    if request is None:
        return None
    try:
        cid = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")
        if cid and isinstance(cid, str):
            cid_clean = cid.strip()
            if 0 < len(cid_clean) <= 128:
                return _sanitize_field(cid_clean, 128)
    except Exception:
        pass
    return None


async def record_audit_event(
    db: AsyncIOMotorDatabase,
    action: str | AuditAction,
    outcome: str | AuditOutcome,
    actor_id: Optional[str] = None,
    document_id: Optional[str] = None,
    status_code: Optional[int] = None,
    reason: Optional[str] = None,
    correlation_id: Optional[str] = None,
    request: Optional[Request] = None,
) -> Optional[dict]:
    """
    Safely persist an audit event into MongoDB 'audit_logs' collection.

    Security & Reliability:
    - Never throws an unhandled exception: fails safely on database or driver error.
    - Strips/bounds strings to avoid runaway memory or payload attacks.
    - Never records passwords, hashes, tokens, document bytes, or filesystem paths.
    """
    if correlation_id is None and request is not None:
        correlation_id = extract_correlation_id(request)

    action_str = action.value if isinstance(action, AuditAction) else str(action)
    outcome_str = outcome.value if isinstance(outcome, AuditOutcome) else str(outcome)

    safe_action = _sanitize_field(action_str, 100) or ""
    safe_outcome = (outcome_str.strip().lower() if outcome_str else "unknown")[:50]
    safe_actor_id = _sanitize_field(actor_id, 100) if actor_id else None
    safe_document_id = _sanitize_field(document_id, 100) if document_id else None
    safe_reason = _sanitize_field(reason, 200) if reason else None
    safe_cid = _sanitize_field(correlation_id, 128) if correlation_id else None

    event_id = str(uuid.uuid4())
    event_doc = {
        "id": event_id,
        "_id": event_id,
        "timestamp": datetime.now(timezone.utc),
        "actor_id": safe_actor_id,
        "action": safe_action,
        "document_id": safe_document_id,
        "outcome": safe_outcome,
        "status_code": status_code,
        "reason": safe_reason,
        "correlation_id": safe_cid,
    }

    try:
        if db is not None and hasattr(db, "__getitem__"):
            await db["audit_logs"].insert_one(event_doc)
            logger.info(
                "Audit event recorded: action=%s outcome=%s actor=%s doc=%s",
                safe_action,
                safe_outcome,
                safe_actor_id,
                safe_document_id,
            )
        return event_doc
    except Exception as exc:
        # Fails safely without exposing secrets or raising to the caller
        logger.error(
            "Audit event logging failed for action %s: %s",
            safe_action,
            exc.__class__.__name__,
        )
        return None
