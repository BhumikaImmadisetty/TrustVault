"""
Integration and API endpoint tests for authentication (Registration & Login).
Uses FastAPI TestClient and mock database to ensure unit testing without a live MongoDB server.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError
from app.api.deps import get_database
from app.core.security import verify_password
from app.main import app


class InMemoryMockUsersCollection:
    """Mock MongoDB users collection storing records in memory for test isolation."""

    def __init__(self):
        self.records = {}

    async def find_one(self, query):
        email = query.get("email")
        if email and email in self.records:
            return dict(self.records[email])
        return None

    async def insert_one(self, doc):
        email = doc["email"]
        self.records[email] = dict(doc)
        mock_result = MagicMock()
        mock_result.inserted_id = doc.get("_id")
        return mock_result


class InMemoryMockDatabase:
    """Mock database returning InMemoryMockUsersCollection for 'users' collection."""

    def __init__(self):
        self.users_col = InMemoryMockUsersCollection()

    def __getitem__(self, collection_name: str):
        if collection_name == "users":
            return self.users_col
        raise KeyError(f"Collection {collection_name} not mocked in InMemoryMockDatabase")


@pytest.fixture
def mock_db():
    """Provides a fresh isolated in-memory mock database for each test."""
    return InMemoryMockDatabase()


@pytest.fixture
def client(mock_db):
    """Provides a TestClient with get_database overridden to the mock database."""
    app.dependency_overrides[get_database] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =========================================================================
# Part A: Registration Endpoint Tests
# =========================================================================

def test_successful_user_registration(client, mock_db):
    """Verify that a valid user can register and receives a 201 Created response."""
    payload = {
        "email": "NewUser@TrustVault.Local",
        "full_name": "Valid Citizen",
        "password": "StrongPassword123!",
    }

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    data = response.json()

    # Public response must have normalized email, full name, and assigned default role
    assert data["email"] == "newuser@trustvault.local"
    assert data["full_name"] == "Valid Citizen"
    assert data["role"] == "viewer"
    assert data["is_active"] is True
    assert "id" in data


def test_registration_stores_password_as_argon2_hash(client, mock_db):
    """Verify that the database stores only the Argon2 hash, never plaintext."""
    raw_password = "PlaintextPassword999!"
    payload = {
        "email": "hashed_check@example.com",
        "full_name": "Hash Verifier",
        "password": raw_password,
    }

    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    stored_record = mock_db.users_col.records.get("hashed_check@example.com")
    assert stored_record is not None

    # Plaintext password must NOT be in the database record
    assert "password" not in stored_record
    assert stored_record.get("hashed_password") != raw_password
    assert raw_password not in stored_record.get("hashed_password")

    # Hash must be an Argon2id hash and verify correctly
    hashed_pwd = stored_record["hashed_password"]
    assert hashed_pwd.startswith("$argon2id$")
    assert verify_password(raw_password, hashed_pwd) is True


def test_registration_never_returns_password_hash_in_response(client):
    """Verify that the API response strictly excludes any password hash."""
    payload = {
        "email": "no_hash_leak@example.com",
        "full_name": "Privacy Advocate",
        "password": "PrivacyPassword123!",
    }

    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "hashed_password" not in data
    assert "password" not in data


def test_duplicate_email_registration_rejected(client):
    """Verify that attempting to register an existing email returns 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "full_name": "First Account",
        "password": "FirstPassword123!",
    }

    # Initial registration
    first_resp = client.post("/api/v1/auth/register", json=payload)
    assert first_resp.status_code == 201

    # Second registration with identical email (different case/whitespace)
    dup_payload = {
        "email": "  DUPLICATE@EXAMPLE.com  ",
        "full_name": "Second Account Attempt",
        "password": "DifferentPassword123!",
    }
    second_resp = client.post("/api/v1/auth/register", json=dup_payload)

    assert second_resp.status_code == 409
    assert "already exists" in second_resp.json()["detail"].lower()


def test_public_registration_cannot_create_admin(client, mock_db):
    """Security test: public registration attempting role='admin' must be rejected."""
    payload = {
        "email": "attacker@example.com",
        "full_name": "Rogue Actor",
        "password": "AttackerPassword123!",
        "role": "admin",
    }

    response = client.post("/api/v1/auth/register", json=payload)

    # Must be rejected at validation level with 422 Unprocessable Entity
    assert response.status_code == 422

    # Verify no record was created in the database
    assert "attacker@example.com" not in mock_db.users_col.records


# =========================================================================
# Part B: Login Endpoint Tests
# =========================================================================

def test_successful_login(client):
    """Verify that valid credentials return 200 OK and a signed JWT access token."""
    email = "login_success@example.com"
    password = "CorrectLoginPassword123!"

    # Register the user
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Login User", "password": password},
    )
    assert reg_resp.status_code == 201

    # Attempt login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert login_resp.status_code == 200
    data = login_resp.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"].split(".")) == 3  # Standard JWT
    assert data["user"]["email"] == email


def test_login_fails_with_incorrect_password(client):
    """Verify that an incorrect password returns generic 401 Unauthorized."""
    email = "wrong_pass_user@example.com"
    password = "ValidRegistrationPass123!"

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "User A", "password": password},
    )

    # Attempt login with wrong password
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword123!"},
    )

    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "Invalid email or password"


def test_login_fails_with_unknown_email(client):
    """Verify that non-existent email returns generic 401 to prevent user enumeration."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "AnyPassword123!"},
    )

    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "Invalid email or password"


def test_login_response_never_exposes_password_hash(client):
    """Verify that login response user payload never exposes password hash."""
    email = "clean_response@example.com"
    password = "CleanResponsePass123!"

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Clean User", "password": password},
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    user_data = login_resp.json()["user"]

    assert "hashed_password" not in user_data
    assert "password" not in user_data


# =========================================================================
# Part C: Error Handling & Resilience Tests
# =========================================================================

def test_registration_handles_database_failure_safely():
    """Verify that database errors during registration return 503 without leaking details."""
    broken_db = MagicMock()
    broken_db.__getitem__.return_value.find_one = AsyncMock(
        side_effect=PyMongoError("Connection reset by peer")
    )

    app.dependency_overrides[get_database] = lambda: broken_db
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/auth/register",
                json={
                    "email": "db_fail@example.com",
                    "full_name": "Broken DB User",
                    "password": "ValidPassword123!",
                },
            )

            assert response.status_code == 503
            assert "temporarily unavailable" in response.json()["detail"]
            # Sensitive internal PyMongo connection message must NOT be leaked
            assert "Connection reset by peer" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_direct_auth_route_path_aliases():
    """Verify that routes are accessible both via /api/v1/auth/register and /auth/register."""
    mock_database = InMemoryMockDatabase()
    app.dependency_overrides[get_database] = lambda: mock_database

    try:
        with TestClient(app) as test_client:
            # Register using direct /auth/register
            reg_resp = test_client.post(
                "/auth/register",
                json={
                    "email": "alias_test@example.com",
                    "full_name": "Alias User",
                    "password": "AliasPassword123!",
                },
            )
            assert reg_resp.status_code == 201

            # Login using direct /auth/login
            login_resp = test_client.post(
                "/auth/login",
                json={"email": "alias_test@example.com", "password": "AliasPassword123!"},
            )
            assert login_resp.status_code == 200
            assert "access_token" in login_resp.json()
    finally:
        app.dependency_overrides.clear()
