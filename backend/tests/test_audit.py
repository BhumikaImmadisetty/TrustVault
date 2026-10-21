"""
Tests for the TrustVault Secure Audit Trail.

Validates that:
- Successful and denied authentication events are audited.
- Successful and denied document operations (upload, download, update, delete) are audited.
- Permission grants and revocations are audited.
- Non-admin access to the audit trail endpoint is forbidden (403).
- Admin access to the audit trail succeeds with accurate pagination and filtering.
- Audit records never leak credentials, passwords, JWTs, file paths, or document contents.
- Audit logging failures are fail-safe and do not disrupt business operations.
"""

import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.api.deps import get_current_user, get_database, require_admin_user
from app.core.audit import record_audit_event
from app.core.security import hash_password
from app.main import app
from app.models.audit import AuditAction, AuditOutcome
from app.models.document import DocumentStatus
from app.models.permission import PermissionLevel
from app.models.user import UserResponse, UserRole


# ---------------------------------------------------------------------------
# Test Helpers & Realistic Mock Data
# ---------------------------------------------------------------------------

PDF_CONTENT = b"%PDF-1.4 minimal test audit content"

def _make_user(
    user_id: str = "user-regular-001",
    email: str = "user@example.com",
    role: UserRole = UserRole.OWNER,
    is_active: bool = True,
) -> UserResponse:
    return UserResponse(
        id=user_id,
        email=email,
        full_name="Regular Test User",
        role=role,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
    )


def _make_admin(
    admin_id: str = "admin-user-999",
    email: str = "admin@trustvault.internal",
) -> UserResponse:
    return UserResponse(
        id=admin_id,
        email=email,
        full_name="Security Administrator",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# In-Memory Mock Collections with Full Audit Support
# ---------------------------------------------------------------------------

class MockCursor:
    """Async-compatible cursor mock supporting sort, skip, limit, and to_list."""

    def __init__(self, records: list[dict]):
        self._records = records
        self._skip_n = 0
        self._limit_n = len(records)

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, str):
            key = key_or_list
            reverse = direction == -1
        elif isinstance(key_or_list, (list, tuple)) and key_or_list:
            key, direction = key_or_list[0]
            reverse = direction == -1
        else:
            return self

        try:
            self._records = sorted(
                self._records,
                key=lambda r: (r.get(key) is not None, r.get(key)),
                reverse=reverse,
            )
        except TypeError:
            pass
        return self

    def skip(self, n: int):
        self._skip_n = max(0, n)
        return self

    def limit(self, n: int):
        self._limit_n = max(0, n)
        return self

    async def to_list(self, length: int | None = None):
        result = self._records[self._skip_n :]
        limit = min(self._limit_n, length) if length is not None else self._limit_n
        return result[:limit]


class InMemoryAuditLogsCollection:
    """Mock MongoDB collection storing audit events in memory."""

    def __init__(self):
        self.records: list[dict] = []

    async def insert_one(self, doc: dict):
        new_doc = dict(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = f"audit-{len(self.records) + 1}"
        self.records.append(new_doc)
        mock_res = MagicMock()
        mock_res.inserted_id = new_doc["_id"]
        return mock_res

    async def count_documents(self, query: dict) -> int:
        return sum(1 for r in self.records if self._matches(r, query))

    def find(self, query: dict):
        matched = [dict(r) for r in self.records if self._matches(r, query)]
        return MockCursor(matched)

    def _matches(self, record: dict, query: dict) -> bool:
        for key, cond in query.items():
            val = record.get(key)
            if key == "id" and val is None:
                val = record.get("_id")

            if isinstance(cond, dict):
                if "$gte" in cond:
                    if val is None or val < cond["$gte"]:
                        return False
                if "$lte" in cond:
                    if val is None or val > cond["$lte"]:
                        return False
                if "$ne" in cond:
                    if val == cond["$ne"]:
                        return False
            else:
                if val != cond:
                    return False
        return True


class InMemoryDocumentsCollection:
    def __init__(self):
        self.records: list[dict] = []

    async def insert_one(self, doc: dict):
        new_doc = dict(doc)
        self.records.append(new_doc)
        res = MagicMock()
        res.inserted_id = new_doc.get("_id")
        return res

    async def find_one(self, query: dict):
        for r in self.records:
            if self._matches(r, query):
                return dict(r)
        return None

    def find(self, query: dict):
        matched = [dict(r) for r in self.records if self._matches(r, query)]
        return MockCursor(matched)

    async def count_documents(self, query: dict) -> int:
        return sum(1 for r in self.records if self._matches(r, query))

    async def update_one(self, query: dict, update: dict):
        res = MagicMock()
        res.matched_count = 0
        res.modified_count = 0
        for r in self.records:
            if self._matches(r, query):
                res.matched_count = 1
                if "$set" in update:
                    for k, v in update["$set"].items():
                        r[k] = v
                    res.modified_count = 1
                return res
        return res

    async def delete_one(self, query: dict):
        res = MagicMock()
        for i, r in enumerate(self.records):
            if self._matches(r, query):
                self.records.pop(i)
                res.deleted_count = 1
                return res
        res.deleted_count = 0
        return res

    def _matches(self, record: dict, query: dict) -> bool:
        if "$or" in query:
            if not any(self._matches(record, branch) for branch in query["$or"]):
                return False
        for k, cond in query.items():
            if k == "$or":
                continue
            val = record.get(k)
            if k == "id" and val is None:
                val = record.get("_id")
            elif k == "_id" and val is None:
                val = record.get("id")
            if isinstance(cond, dict):
                if "$ne" in cond and val == cond["$ne"]:
                    return False
            elif val != cond:
                return False
        return True


class InMemoryPermissionsCollection:
    def __init__(self):
        self.records: list[dict] = []

    async def insert_one(self, doc: dict):
        new_doc = dict(doc)
        self.records.append(new_doc)
        res = MagicMock()
        res.inserted_id = new_doc.get("_id")
        return res

    async def find_one(self, query: dict):
        for r in self.records:
            if self._matches(r, query):
                return dict(r)
        return None

    def find(self, query: dict):
        matched = [dict(r) for r in self.records if self._matches(r, query)]
        return MockCursor(matched)

    async def delete_one(self, query: dict):
        res = MagicMock()
        for i, r in enumerate(self.records):
            if self._matches(r, query):
                self.records.pop(i)
                res.deleted_count = 1
                return res
        res.deleted_count = 0
        return res

    async def delete_many(self, query: dict):
        res = MagicMock()
        initial_len = len(self.records)
        self.records = [r for r in self.records if not self._matches(r, query)]
        res.deleted_count = initial_len - len(self.records)
        return res

    def _matches(self, record: dict, query: dict) -> bool:
        for k, v in query.items():
            if record.get(k) != v:
                return False
        return True


class InMemoryUsersCollection:
    def __init__(self):
        self.records: list[dict] = []

    async def insert_one(self, doc: dict):
        new_doc = dict(doc)
        self.records.append(new_doc)
        res = MagicMock()
        res.inserted_id = new_doc.get("_id")
        return res

    async def find_one(self, query: dict):
        for r in self.records:
            if self._matches(r, query):
                return dict(r)
        return None

    def _matches(self, record: dict, query: dict) -> bool:
        if "$or" in query:
            return any(self._matches(record, branch) for branch in query["$or"])
        for k, v in query.items():
            val = record.get(k)
            if k == "id" and val is None:
                val = record.get("_id")
            elif k == "_id" and val is None:
                val = record.get("id")
            if val != v:
                return False
        return True


class InMemoryMockDatabaseWithAudit:
    """Mock database with audit_logs, documents, permissions, and users collections."""

    def __init__(self):
        self.documents_col = InMemoryDocumentsCollection()
        self.permissions_col = InMemoryPermissionsCollection()
        self.users_col = InMemoryUsersCollection()
        self.audit_logs_col = InMemoryAuditLogsCollection()

    def __getitem__(self, name: str):
        if name == "audit_logs":
            return self.audit_logs_col
        elif name == "documents":
            return self.documents_col
        elif name == "permissions":
            return self.permissions_col
        elif name == "users":
            return self.users_col
        raise KeyError(f"Collection '{name}' not mocked")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    return InMemoryMockDatabaseWithAudit()


@pytest.fixture
def test_user():
    return _make_user(user_id="user-owner-1", email="owner@example.com")


@pytest.fixture
def test_admin():
    return _make_admin()


@pytest.fixture
def other_user():
    return _make_user(user_id="user-other-2", email="other@example.com", role=UserRole.VIEWER)


@pytest.fixture
def client(mock_db, test_user, tmp_path):
    app.dependency_overrides[get_database] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    with patch("app.api.v1.endpoints.documents.settings") as mock_settings:
        mock_settings.max_upload_size_bytes = 10 * 1024 * 1024
        mock_settings.MAX_UPLOAD_SIZE_MB = 10
        mock_settings.STORAGE_PATH = str(tmp_path)
        with patch("app.api.v1.endpoints.documents._resolve_storage_root", return_value=tmp_path):
            with TestClient(app) as test_client:
                try:
                    yield test_client
                finally:
                    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(mock_db, test_admin):
    app.dependency_overrides[get_database] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: test_admin
    app.dependency_overrides[require_admin_user] = lambda: test_admin
    with TestClient(app) as test_client:
        try:
            yield test_client
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Part A: Document Action Auditing Tests
# ---------------------------------------------------------------------------

def test_document_upload_creates_audit_event(client, mock_db, test_user):
    """Uploading a document must create a successful document.upload audit record."""
    files = {"file": ("contract.pdf", io.BytesIO(PDF_CONTENT), "application/pdf")}
    data = {"title": "Service Contract", "description": "Audit trail test"}

    resp = client.post("/api/v1/documents/upload", files=files, data=data)
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    audit_records = mock_db.audit_logs_col.records
    upload_events = [r for r in audit_records if r.get("action") == AuditAction.DOCUMENT_UPLOAD.value]

    assert len(upload_events) == 1
    event = upload_events[0]
    assert event["outcome"] == AuditOutcome.SUCCESS.value
    assert event["actor_id"] == test_user.id
    assert event["document_id"] == doc_id
    assert event["status_code"] == 201
    assert "timestamp" in event
    assert "id" in event


def test_document_download_success_creates_audit_event(client, mock_db, test_user, tmp_path):
    """Downloading a document as owner must create a successful document.download audit record."""
    file_path = tmp_path / "test_download.pdf"
    file_path.write_bytes(PDF_CONTENT)

    mock_db.documents_col.records.append({
        "_id": "doc-down-001",
        "title": "Download Test",
        "owner_id": test_user.id,
        "storage_path": str(file_path),
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": len(PDF_CONTENT),
        "content_type": "application/pdf",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.get("/api/v1/documents/doc-down-001/download")
    assert resp.status_code == 200

    download_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_DOWNLOAD.value and r.get("outcome") == AuditOutcome.SUCCESS.value
    ]
    assert len(download_events) == 1
    assert download_events[0]["actor_id"] == test_user.id
    assert download_events[0]["document_id"] == "doc-down-001"
    assert download_events[0]["status_code"] == 200


def test_document_download_denied_creates_audit_event(client, mock_db, test_user, other_user, tmp_path):
    """Downloading a document without permission must create a denied document.download audit record."""
    file_path = tmp_path / "private_doc.pdf"
    file_path.write_bytes(PDF_CONTENT)

    # Document owned by other_user, test_user has NO permission
    mock_db.documents_col.records.append({
        "_id": "doc-private-999",
        "title": "Private Document",
        "owner_id": other_user.id,
        "storage_path": str(file_path),
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": len(PDF_CONTENT),
        "content_type": "application/pdf",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.get("/api/v1/documents/doc-private-999/download")
    assert resp.status_code == 403

    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_DOWNLOAD.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == test_user.id
    assert denied_events[0]["document_id"] == "doc-private-999"
    assert denied_events[0]["status_code"] == 403


def test_document_download_nonexistent_creates_denied_audit(client, mock_db, test_user):
    """Attempting to download a non-existent document records a denied audit event."""
    resp = client.get("/api/v1/documents/doc-does-not-exist/download")
    assert resp.status_code == 404

    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_DOWNLOAD.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == test_user.id
    assert denied_events[0]["document_id"] == "doc-does-not-exist"
    assert denied_events[0]["status_code"] == 404


def test_document_metadata_update_success_audited(client, mock_db, test_user):
    """Successful metadata update creates a document.update success audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-meta-001",
        "filename": "old_contract.pdf",
        "description": "Old Description",
        "owner_id": test_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 100,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.patch(
        "/api/v1/documents/doc-meta-001",
        json={"filename": "updated_contract.pdf", "description": "Updated Description"},
    )
    assert resp.status_code == 200

    update_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_UPDATE.value and r.get("outcome") == AuditOutcome.SUCCESS.value
    ]
    assert len(update_events) == 1
    assert update_events[0]["actor_id"] == test_user.id
    assert update_events[0]["document_id"] == "doc-meta-001"
    assert update_events[0]["status_code"] == 200


def test_document_metadata_update_denied_audited(client, mock_db, test_user, other_user):
    """Attempted metadata update by read-only user creates a document.update denied audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-meta-002",
        "filename": "protected_doc.pdf",
        "owner_id": other_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 100,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    # Grant READ permission only
    mock_db.permissions_col.records.append({
        "_id": "perm-read-only",
        "document_id": "doc-meta-002",
        "grantee_id": test_user.id,
        "permission_level": PermissionLevel.READ.value,
        "granted_by": other_user.id,
        "created_at": datetime.now(timezone.utc),
    })

    resp = client.patch("/api/v1/documents/doc-meta-002", json={"filename": "unauthorized_edit.pdf"})
    assert resp.status_code == 403

    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_UPDATE.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == test_user.id
    assert denied_events[0]["document_id"] == "doc-meta-002"
    assert denied_events[0]["status_code"] == 403


def test_document_delete_success_audited(client, mock_db, test_user):
    """Deleting a document by owner creates a document.delete success audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-del-001",
        "filename": "delete_me.pdf",
        "owner_id": test_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 100,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.delete("/api/v1/documents/doc-del-001")
    assert resp.status_code == 204

    del_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_DELETE.value and r.get("outcome") == AuditOutcome.SUCCESS.value
    ]
    assert len(del_events) == 1
    assert del_events[0]["actor_id"] == test_user.id
    assert del_events[0]["document_id"] == "doc-del-001"
    assert del_events[0]["status_code"] == 204


def test_document_delete_denied_audited(client, mock_db, test_user, other_user):
    """Attempting to delete another user's document creates a document.delete denied audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-del-002",
        "title": "Not Mine",
        "owner_id": other_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 100,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.delete("/api/v1/documents/doc-del-002")
    assert resp.status_code == 403

    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.DOCUMENT_DELETE.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == test_user.id
    assert denied_events[0]["document_id"] == "doc-del-002"
    assert denied_events[0]["status_code"] == 403


# ---------------------------------------------------------------------------
# Part B: Permission Grant & Revocation Auditing Tests
# ---------------------------------------------------------------------------

def test_permission_grant_success_audited(client, mock_db, test_user, other_user):
    """Owner granting permission creates a permission.grant success audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-perm-001",
        "title": "Share Document",
        "owner_id": test_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 50,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    mock_db.users_col.records.append({
        "_id": other_user.id,
        "id": other_user.id,
        "email": other_user.email,
        "is_active": True,
    })

    resp = client.post(
        "/api/v1/documents/doc-perm-001/permissions",
        json={"grantee_id": other_user.id, "permission_level": "read"},
    )
    assert resp.status_code == 201

    grant_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.PERMISSION_GRANT.value and r.get("outcome") == AuditOutcome.SUCCESS.value
    ]
    assert len(grant_events) == 1
    assert grant_events[0]["actor_id"] == test_user.id
    assert grant_events[0]["document_id"] == "doc-perm-001"
    assert grant_events[0]["status_code"] == 201


def test_permission_grant_denied_for_non_owner(client, mock_db, test_user, other_user):
    """Non-owner attempting to grant permission creates a permission.grant denied audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-perm-002",
        "title": "Other's Document",
        "owner_id": other_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 50,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.post(
        "/api/v1/documents/doc-perm-002/permissions",
        json={"grantee_id": test_user.id, "permission_level": "edit"},
    )
    assert resp.status_code == 403

    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.PERMISSION_GRANT.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == test_user.id
    assert denied_events[0]["document_id"] == "doc-perm-002"
    assert denied_events[0]["status_code"] == 403


def test_permission_revoke_success_audited(client, mock_db, test_user, other_user):
    """Owner revoking permission creates a permission.revoke success audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-perm-003",
        "title": "Revoke Document",
        "owner_id": test_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 50,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    mock_db.permissions_col.records.append({
        "_id": "perm-to-revoke",
        "document_id": "doc-perm-003",
        "grantee_id": other_user.id,
        "permission_level": "read",
        "granted_by": test_user.id,
        "created_at": datetime.now(timezone.utc),
    })

    resp = client.delete(f"/api/v1/documents/doc-perm-003/permissions/{other_user.id}")
    assert resp.status_code == 204

    revoke_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.PERMISSION_REVOKE.value and r.get("outcome") == AuditOutcome.SUCCESS.value
    ]
    assert len(revoke_events) == 1
    assert revoke_events[0]["actor_id"] == test_user.id
    assert revoke_events[0]["document_id"] == "doc-perm-003"
    assert revoke_events[0]["status_code"] == 204


def test_permission_revoke_denied_for_non_owner(client, mock_db, test_user, other_user):
    """Non-owner attempting to revoke permission creates a permission.revoke denied audit record."""
    mock_db.documents_col.records.append({
        "_id": "doc-perm-004",
        "title": "Revoke Non Owner",
        "owner_id": other_user.id,
        "status": DocumentStatus.ACTIVE.value,
        "size_bytes": 50,
        "content_type": "application/pdf",
        "storage_path": "/tmp/dummy",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    resp = client.delete(f"/api/v1/documents/doc-perm-004/permissions/{other_user.id}")
    assert resp.status_code == 403

    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.PERMISSION_REVOKE.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == test_user.id
    assert denied_events[0]["document_id"] == "doc-perm-004"
    assert denied_events[0]["status_code"] == 403


# ---------------------------------------------------------------------------
# Part C: Authentication Auditing Tests (Login Success & Denied)
# ---------------------------------------------------------------------------

def test_login_success_creates_audit_event(mock_db):
    """Successful login must record an auth.login success audit event."""
    password = "SecurePassword123!"
    hashed = hash_password(password)
    user_record = {
        "_id": "user-login-001",
        "id": "user-login-001",
        "email": "auditlogin@example.com",
        "hashed_password": hashed,
        "full_name": "Audit Login User",
        "role": UserRole.VIEWER.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    mock_db.users_col.records.append(user_record)

    app.dependency_overrides[get_database] = lambda: mock_db
    with TestClient(app) as auth_client:
        resp = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "auditlogin@example.com", "password": password},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    login_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.LOGIN.value and r.get("outcome") == AuditOutcome.SUCCESS.value
    ]
    assert len(login_events) == 1
    assert login_events[0]["actor_id"] == "user-login-001"
    assert login_events[0]["status_code"] == 200


def test_login_failure_creates_denied_audit_event(mock_db):
    """Failed login attempt with incorrect password records an auth.login denied audit event."""
    password = "CorrectPassword123!"
    hashed = hash_password(password)
    user_record = {
        "_id": "user-login-002",
        "id": "user-login-002",
        "email": "failedlogin@example.com",
        "hashed_password": hashed,
        "full_name": "Failed Login User",
        "role": UserRole.VIEWER.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    mock_db.users_col.records.append(user_record)

    app.dependency_overrides[get_database] = lambda: mock_db
    with TestClient(app) as auth_client:
        resp = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "failedlogin@example.com", "password": "WrongPassword!"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 401
    denied_events = [
        r for r in mock_db.audit_logs_col.records
        if r.get("action") == AuditAction.LOGIN.value and r.get("outcome") == AuditOutcome.DENIED.value
    ]
    assert len(denied_events) == 1
    assert denied_events[0]["actor_id"] == "user-login-002"
    assert denied_events[0]["status_code"] == 401


# ---------------------------------------------------------------------------
# Part D: Admin Audit View Authorization & Inspection Tests
# ---------------------------------------------------------------------------

def test_admin_can_access_audit_logs(admin_client, mock_db):
    """Admin users can retrieve audit events successfully (200 OK)."""
    now = datetime.now(timezone.utc)
    mock_db.audit_logs_col.records.append({
        "_id": "ev-01",
        "timestamp": now,
        "actor_id": "user-1",
        "action": AuditAction.DOCUMENT_UPLOAD.value,
        "document_id": "doc-101",
        "outcome": AuditOutcome.SUCCESS.value,
        "status_code": 201,
        "reason": "Document uploaded successfully",
        "correlation_id": "corr-abc-123",
    })

    resp = admin_client.get("/api/v1/audit/")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 1
    assert len(data["events"]) == 1
    ev = data["events"][0]
    assert ev["action"] == AuditAction.DOCUMENT_UPLOAD.value
    assert ev["outcome"] == "success"
    assert ev["document_id"] == "doc-101"
    assert ev["correlation_id"] == "corr-abc-123"


def test_non_admin_cannot_access_audit_logs(client):
    """Non-admin user (e.g., OWNER role) attempting to access audit endpoint gets 403 Forbidden."""
    resp = client.get("/api/v1/audit/")
    assert resp.status_code == 403
    assert "administrator" in resp.json()["detail"].lower()


def test_unauthenticated_request_to_audit_logs_rejected():
    """Unauthenticated request to audit endpoint gets 401 Unauthorized."""
    app.dependency_overrides.clear()
    with TestClient(app) as raw_client:
        resp = raw_client.get("/api/v1/audit/")
    assert resp.status_code == 401


def test_audit_logs_pagination(admin_client, mock_db):
    """Admin endpoint supports pagination with skip and limit."""
    now = datetime.now(timezone.utc)
    for i in range(10):
        mock_db.audit_logs_col.records.append({
            "_id": f"ev-{i:02d}",
            "timestamp": now + timedelta(seconds=i),
            "actor_id": f"user-{i}",
            "action": AuditAction.DOCUMENT_UPLOAD.value,
            "document_id": f"doc-{i}",
            "outcome": AuditOutcome.SUCCESS.value,
            "status_code": 201,
        })

    resp = admin_client.get("/api/v1/audit/?skip=2&limit=3")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 10
    assert data["skip"] == 2
    assert data["limit"] == 3
    assert len(data["events"]) == 3


def test_audit_logs_filtering_by_action_and_outcome(admin_client, mock_db):
    """Audit logs can be filtered by action and outcome."""
    now = datetime.now(timezone.utc)
    mock_db.audit_logs_col.records.extend([
        {
            "_id": "ev-1",
            "timestamp": now,
            "actor_id": "u1",
            "action": AuditAction.DOCUMENT_UPLOAD.value,
            "outcome": AuditOutcome.SUCCESS.value,
            "status_code": 201,
        },
        {
            "_id": "ev-2",
            "timestamp": now + timedelta(seconds=1),
            "actor_id": "u2",
            "action": AuditAction.DOCUMENT_DOWNLOAD.value,
            "outcome": AuditOutcome.DENIED.value,
            "status_code": 403,
        },
        {
            "_id": "ev-3",
            "timestamp": now + timedelta(seconds=2),
            "actor_id": "u3",
            "action": AuditAction.DOCUMENT_DOWNLOAD.value,
            "outcome": AuditOutcome.SUCCESS.value,
            "status_code": 200,
        },
    ])

    # Filter by action
    resp = admin_client.get(f"/api/v1/audit/?action={AuditAction.DOCUMENT_DOWNLOAD.value}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for ev in data["events"]:
        assert ev["action"] == AuditAction.DOCUMENT_DOWNLOAD.value

    # Filter by outcome
    resp_outcome = admin_client.get("/api/v1/audit/?outcome=denied")
    assert resp_outcome.status_code == 200
    data_outcome = resp_outcome.json()
    assert data_outcome["total"] == 1
    assert data_outcome["events"][0]["outcome"] == "denied"
    assert data_outcome["events"][0]["status_code"] == 403


def test_audit_logs_filtering_by_date_range(admin_client, mock_db):
    """Audit logs can be filtered by start_date and end_date."""
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 3, 12, 0, 0, tzinfo=timezone.utc)

    mock_db.audit_logs_col.records.extend([
        {"_id": "e1", "timestamp": t0, "action": "document.upload", "outcome": "success"},
        {"_id": "e2", "timestamp": t1, "action": "document.download", "outcome": "success"},
        {"_id": "e3", "timestamp": t2, "action": "document.delete", "outcome": "success"},
    ])

    start_iso = "2026-01-02T00:00:00Z"
    end_iso = "2026-01-02T23:59:59Z"
    resp = admin_client.get(f"/api/v1/audit/?start_date={start_iso}&end_date={end_iso}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["events"][0]["action"] == "document.download"


# ---------------------------------------------------------------------------
# Part E: Security & Sensitive Data Leak Prevention
# ---------------------------------------------------------------------------

def test_audit_records_never_contain_sensitive_information(mock_db):
    """
    Ensure record_audit_event sanitizes reason and never records passwords,
    hashes, tokens, headers, storage paths, or file contents.
    """
    sensitive_reason = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret password=SuperSecretPassword123 /var/data/storage/doc.pdf"
    
    import asyncio
    asyncio.run(
        record_audit_event(
            db=mock_db,
            action=AuditAction.DOCUMENT_DOWNLOAD,
            outcome=AuditOutcome.DENIED,
            actor_id="user-attacker",
            document_id="doc-secret",
            status_code=403,
            reason=sensitive_reason,
        )
    )

    assert len(mock_db.audit_logs_col.records) == 1
    rec = mock_db.audit_logs_col.records[0]

    # Verify absence of forbidden keys
    forbidden_keys = [
        "password",
        "hashed_password",
        "token",
        "access_token",
        "storage_path",
        "content",
        "file_bytes",
        "authorization",
    ]
    for key in forbidden_keys:
        assert key not in rec, f"Forbidden key '{key}' found in audit record"

    # Verify reason is sanitized (redacted)
    reason = rec.get("reason", "")
    assert "SuperSecretPassword123" not in reason
    assert "eyJhbGci" not in reason
    assert "/var/data" not in reason


def test_audit_failure_is_fail_safe_and_does_not_break_upload(client, mock_db, test_user):
    """
    If the audit collection throws an unexpected database exception,
    the main operation (upload) must still succeed (fail-safe audit logging).
    """
    # Cause insert_one on audit_logs to raise an exception
    async def failing_insert(*args, **kwargs):
        raise PyMongoError("Audit database connection dropped")

    mock_db.audit_logs_col.insert_one = failing_insert

    files = {"file": ("failsafe.pdf", io.BytesIO(PDF_CONTENT), "application/pdf")}
    data = {"title": "Failsafe Test", "description": "Audit failure must not crash upload"}

    resp = client.post("/api/v1/documents/upload", files=files, data=data)
    assert resp.status_code == 201
    assert "id" in resp.json()
