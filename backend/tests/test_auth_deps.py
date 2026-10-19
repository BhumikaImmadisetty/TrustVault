"""
Automated unit tests for get_current_user dependency and protected endpoints.
Tests token extraction, validation, error safety, and database-driven role resolution
without requiring a live MongoDB server.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError
from app.api.deps import get_database
from app.core.security import create_access_token
from app.main import app
from app.models.user import UserRole


class InMemoryMockUsersCollection:
    """Mock MongoDB users collection supporting lookup by email or user ID."""

    def __init__(self):
        self.by_email = {}
        self.by_id = {}

    def add_user(self, user_doc: dict):
        uid = str(user_doc.get("id") or user_doc.get("_id"))
        email = user_doc["email"].lower()
        doc = dict(user_doc)
        doc["id"] = uid
        doc["_id"] = uid
        self.by_email[email] = doc
        self.by_id[uid] = doc

    async def find_one(self, query):
        if "email" in query:
            email = query["email"].lower()
            if email in self.by_email:
                return dict(self.by_email[email])

        if "$or" in query:
            for clause in query["$or"]:
                if "id" in clause and clause["id"] in self.by_id:
                    return dict(self.by_id[clause["id"]])
                if "_id" in clause and clause["_id"] in self.by_id:
                    return dict(self.by_id[clause["_id"]])

        return None


class InMemoryMockDatabase:
    """Mock database returning InMemoryMockUsersCollection."""

    def __init__(self):
        self.users_col = InMemoryMockUsersCollection()

    def __getitem__(self, name: str):
        if name == "users":
            return self.users_col
        raise KeyError(name)


@pytest.fixture
def mock_db():
    return InMemoryMockDatabase()


@pytest.fixture
def client(mock_db):
    app.dependency_overrides[get_database] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =========================================================================
# Token Extraction & Validation Tests
# =========================================================================

def test_missing_authorization_header(client):
    """Verify that omitting the Authorization header returns 401 with standard challenge."""
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "credentials were not provided" in response.json()["detail"].lower()


def test_malformed_bearer_token(client):
    """Verify that non-Bearer schemes or corrupted token strings return 401."""
    # Wrong scheme (Basic instead of Bearer)
    basic_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert basic_resp.status_code == 401
    assert "bearer token required" in basic_resp.json()["detail"].lower()

    # Empty bearer token
    empty_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer "},
    )
    assert empty_resp.status_code == 401

    # Malformed non-JWT string
    malformed_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert malformed_resp.status_code == 401


def test_expired_token_rejected(client, mock_db):
    """Verify that an expired token is rejected with 401 and an expired message."""
    user_id = "user-expired-123"
    mock_db.users_col.add_user({
        "id": user_id,
        "email": "expired@trustvault.local",
        "full_name": "Expired User",
        "role": UserRole.VIEWER.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    })

    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-10),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_tampered_token_rejected(client, mock_db):
    """Verify that a modified or tampered token fails signature verification with 401."""
    user_id = "user-tamper-456"
    mock_db.users_col.add_user({
        "id": user_id,
        "email": "tamper@trustvault.local",
        "full_name": "Tamper Test",
        "role": UserRole.VIEWER.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    })

    token = create_access_token(subject=user_id)
    parts = token.split(".")
    tampered_sig = parts[2][:-4] + ("ZZZZ" if not parts[2].endswith("ZZZZ") else "AAAA")
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401
    assert "could not validate credentials" in response.json()["detail"].lower()


# =========================================================================
# Database Verification & User Resolution Tests
# =========================================================================

def test_valid_token_for_existing_user(client, mock_db):
    """Verify that a valid token resolves the user record and returns UserResponse."""
    user_id = "user-valid-789"
    mock_db.users_col.add_user({
        "id": user_id,
        "email": "alice@trustvault.local",
        "full_name": "Alice Smith",
        "role": UserRole.OWNER.value,
        "is_active": True,
        "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$dummyhashvalue...",
        "created_at": datetime.now(timezone.utc),
    })

    token = create_access_token(subject=user_id)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == user_id
    assert data["email"] == "alice@trustvault.local"
    assert data["full_name"] == "Alice Smith"
    assert data["role"] == "owner"
    assert data["is_active"] is True

    # Critical security assertion: password hash must NEVER leak
    assert "hashed_password" not in data
    assert "password" not in data


def test_token_for_nonexistent_user(client):
    """Verify that a cryptographically valid token for a deleted/nonexistent user is rejected."""
    token = create_access_token(subject="ghost-user-id-999")

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert "does not exist" in response.json()["detail"].lower()


def test_token_for_deactivated_user(client, mock_db):
    """Verify that a deactivated user account is rejected even with a valid token."""
    user_id = "user-deactivated-001"
    mock_db.users_col.add_user({
        "id": user_id,
        "email": "deactivated@trustvault.local",
        "full_name": "Deactivated User",
        "role": UserRole.VIEWER.value,
        "is_active": False,  # Suspended account
        "created_at": datetime.now(timezone.utc),
    })

    token = create_access_token(subject=user_id)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"].lower()


def test_database_unavailable_during_authentication():
    """Verify that database errors during get_current_user return 503 without leaking details."""
    broken_db = MagicMock()
    broken_db.__getitem__.return_value.find_one = AsyncMock(
        side_effect=PyMongoError("Cluster network unreachable")
    )

    app.dependency_overrides[get_database] = lambda: broken_db
    try:
        with TestClient(app) as test_client:
            token = create_access_token(subject="any-valid-uuid")
            response = test_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 503
            assert "temporarily unavailable" in response.json()["detail"]
            assert "Cluster network unreachable" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_current_role_is_taken_from_database_not_token(client, mock_db):
    """
    Requirement 8 Verification:
    Verify that role claims in tokens are completely ignored and the live role
    is fetched dynamically from MongoDB on every request.
    """
    user_id = "user-dynamic-role-123"

    # User in database is a VIEWER
    mock_db.users_col.add_user({
        "id": user_id,
        "email": "dynamic@trustvault.local",
        "full_name": "Dynamic Role User",
        "role": UserRole.VIEWER.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    })

    # Attacker forged a token containing role="admin"
    forged_token = create_access_token(
        subject=user_id,
        additional_claims={"role": "admin"},
    )

    # First request: database says VIEWER
    resp1 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["role"] == "viewer"  # Forged 'admin' claim ignored!

    # Role elevated in database to OWNER
    mock_db.users_col.by_id[user_id]["role"] = UserRole.OWNER.value

    # Second request: using the EXACT same token, role is now live-evaluated as OWNER
    resp2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["role"] == "owner"
