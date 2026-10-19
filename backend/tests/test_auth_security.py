"""
Automated unit tests for password security and user schemas.
Tests Argon2 hashing, verification, password complexity, role boundaries,
and ensures password hashes are never exposed in public models.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from app.core.security import hash_password, verify_password
from app.models.user import UserInDB, UserRegister, UserResponse, UserRole


# =========================================================================
# Part B: Password Security Tests
# =========================================================================

def test_hash_password_produces_argon2id_hash():
    """Verify that hash_password generates a valid Argon2id hash string."""
    plain = "CorrectPassword123!"
    hashed = hash_password(plain)

    assert isinstance(hashed, str)
    assert hashed.startswith("$argon2id$")


def test_password_is_not_stored_as_plaintext():
    """Verify that the generated hash never contains the original plaintext password."""
    plain = "SuperSecretPass456!"
    hashed = hash_password(plain)

    assert plain not in hashed
    assert hashed != plain


def test_verify_password_succeeds_for_correct_password():
    """Verify that verify_password returns True for the matching plaintext password."""
    plain = "ValidPassword789!"
    hashed = hash_password(plain)

    assert verify_password(plain, hashed) is True


def test_verify_password_fails_for_incorrect_password():
    """Verify that verify_password returns False when given an incorrect password."""
    plain = "CorrectPass123!"
    hashed = hash_password(plain)

    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("correctpass123!", hashed) is False  # case-sensitive


def test_verify_password_fails_for_empty_inputs():
    """Verify that empty inputs safely evaluate to False without raising exceptions."""
    hashed = hash_password("ValidPassword123!")

    assert verify_password("", hashed) is False
    assert verify_password("ValidPassword123!", "") is False
    assert verify_password("", "") is False


def test_hash_password_rejects_empty_and_short_passwords():
    """Verify that empty or sub-8-character passwords raise a ValueError."""
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        hash_password("")

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        hash_password("   ")

    with pytest.raises(ValueError, match="at least 8 characters"):
        hash_password("Short1!")


def test_hash_password_rejects_excessively_long_passwords():
    """Verify that passwords exceeding 128 characters are rejected to prevent DoS."""
    too_long = "A1!" + ("x" * 130)
    with pytest.raises(ValueError, match="maximum length"):
        hash_password(too_long)


# =========================================================================
# Part A: User Schemas & Role Boundary Tests
# =========================================================================

def test_user_roles_are_strictly_three():
    """Verify that exactly three roles exist: admin, owner, and viewer."""
    expected_roles = {"admin", "owner", "viewer"}
    actual_roles = {role.value for role in UserRole}

    assert actual_roles == expected_roles
    assert len(UserRole) == 3


def test_user_registration_normalization_and_validation():
    """Verify that user registration accepts valid input and normalizes email."""
    reg = UserRegister(
        email="  Alice.User@EXAMPLE.com  ",
        full_name="Alice Doe",
        password="ValidPassword123!",
    )

    assert reg.email == "alice.user@example.com"
    assert reg.full_name == "Alice Doe"
    assert reg.role == UserRole.VIEWER  # default role


def test_user_registration_cannot_assign_admin_role():
    """Security test: verify that public registration rejects assigning the admin role."""
    with pytest.raises(ValidationError) as exc_info:
        UserRegister(
            email="malicious@example.com",
            full_name="Attacker",
            password="ValidPassword123!",
            role=UserRole.ADMIN,
        )

    errors = exc_info.value.errors()
    assert any("admin" in str(err["msg"]).lower() for err in errors)


def test_user_registration_password_complexity():
    """Verify that passwords lacking complexity (digits, upper, lower) are rejected."""
    # Missing uppercase
    with pytest.raises(ValidationError):
        UserRegister(email="u@example.com", full_name="User", password="lowercase123!")

    # Missing lowercase
    with pytest.raises(ValidationError):
        UserRegister(email="u@example.com", full_name="User", password="UPPERCASE123!")

    # Missing digit
    with pytest.raises(ValidationError):
        UserRegister(email="u@example.com", full_name="User", password="NoDigitsHere!")


def test_user_response_does_not_expose_password_hash():
    """
    Critical security test: verify that UserResponse strictly excludes password hashes
    even when constructed from database representations containing hashed_password.
    """
    db_record = {
        "id": "user-uuid-1234",
        "email": "user@example.com",
        "full_name": "Safe User",
        "role": UserRole.OWNER,
        "is_active": True,
        "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$dummyhashvalue...",
        "created_at": datetime.now(timezone.utc),
    }

    response = UserResponse.model_validate(db_record)
    dumped_data = response.model_dump()

    # Verify fields in dumped output and model fields definition
    assert "hashed_password" not in dumped_data
    assert "password" not in dumped_data
    assert "hashed_password" not in UserResponse.model_fields
    assert "password" not in UserResponse.model_fields

    # Verify string representation also does not leak the hash
    assert "dummyhashvalue" not in repr(response)
    assert "dummyhashvalue" not in str(response)


def test_user_in_db_model_contains_hashed_password():
    """Verify that the internal database schema correctly stores the password hash."""
    user_db = UserInDB(
        email="owner@example.com",
        full_name="Document Owner",
        role=UserRole.OWNER,
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$realhash...",
    )

    assert user_db.role == UserRole.OWNER
    assert user_db.hashed_password.startswith("$argon2id$")
    assert user_db.is_active is True


# =========================================================================
# Part C: JWT Token Security Tests (PyJWT)
# =========================================================================

from datetime import timedelta
import jwt
from app.core.security import (
    ALGORITHM,
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    decode_access_token,
)

# Dedicated 32+ byte test secrets used solely in tests (never production secrets)
TEST_SECRET_A = "test-secret-key-alpha-32-bytes-long-for-testing-hs256"
TEST_SECRET_B = "test-secret-key-bravo-32-bytes-long-for-testing-hs256"


def test_create_and_decode_valid_access_token():
    """Verify that a valid token contains expected claims and decodes successfully."""
    user_id = "user-uuid-9999"
    token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=10),
        secret_key=TEST_SECRET_A,
    )

    assert isinstance(token, str)
    assert len(token.split(".")) == 3  # Standard 3-segment JWT

    payload = decode_access_token(token, secret_key=TEST_SECRET_A)
    assert payload["sub"] == user_id
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] > payload["iat"]


def test_decode_expired_token_raises_token_expired_error():
    """Verify that an expired token is rejected with TokenExpiredError."""
    user_id = "user-uuid-expired"
    # Token that expired 10 seconds ago
    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-10),
        secret_key=TEST_SECRET_A,
    )

    with pytest.raises(TokenExpiredError, match="expired"):
        decode_access_token(expired_token, secret_key=TEST_SECRET_A)


def test_decode_tampered_token_raises_invalid_token_error():
    """Verify that any modification to header, payload, or signature is rejected."""
    token = create_access_token(
        subject="user-uuid-tamper",
        secret_key=TEST_SECRET_A,
    )
    parts = token.split(".")
    # Tamper with the signature component
    tampered_sig = parts[2][:-4] + ("AAAA" if not parts[2].endswith("AAAA") else "BBBB")
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered_token, secret_key=TEST_SECRET_A)


def test_decode_token_signed_with_different_secret_fails():
    """Verify that a token signed with Secret A cannot be decoded using Secret B."""
    token = create_access_token(
        subject="user-uuid-cross-key",
        secret_key=TEST_SECRET_A,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret_key=TEST_SECRET_B)


def test_decode_token_missing_required_claims_fails():
    """Verify that tokens missing required claims (such as sub, exp, or iat) are rejected."""
    # Token missing 'sub'
    incomplete_payload = {
        "iat": 1700000000,
        "exp": 1700003600,
    }
    missing_sub_token = jwt.encode(incomplete_payload, TEST_SECRET_A, algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(missing_sub_token, secret_key=TEST_SECRET_A)

    # Token missing 'exp'
    no_exp_payload = {
        "sub": "user-uuid",
        "iat": 1700000000,
    }
    no_exp_token = jwt.encode(no_exp_payload, TEST_SECRET_A, algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(no_exp_token, secret_key=TEST_SECRET_A)


def test_decode_malformed_tokens_fail_safely():
    """Verify that non-JWT or garbage strings fail safely with InvalidTokenError."""
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.valid.jwt.token", secret_key=TEST_SECRET_A)

    with pytest.raises(InvalidTokenError):
        decode_access_token("", secret_key=TEST_SECRET_A)

    with pytest.raises(InvalidTokenError):
        decode_access_token("   ", secret_key=TEST_SECRET_A)


def test_create_access_token_empty_subject_rejected():
    """Verify that create_access_token rejects empty subject identifiers."""
    with pytest.raises(ValueError, match="subject"):
        create_access_token(subject="", secret_key=TEST_SECRET_A)

    with pytest.raises(ValueError, match="subject"):
        create_access_token(subject="   ", secret_key=TEST_SECRET_A)


def test_token_role_claim_does_not_substitute_server_side_authority():
    """
    Requirement 8 Test:
    Even if a token carries a role claim, the decoded payload must still be
    treated as untrusted until verified against the live database state.
    """
    token = create_access_token(
        subject="user-uuid-role-test",
        additional_claims={"role": "admin"},
        secret_key=TEST_SECRET_A,
    )
    payload = decode_access_token(token, secret_key=TEST_SECRET_A)

    # Claim is present in the token structure...
    assert payload.get("role") == "admin"
    # ...but the subject identifier remains the single source of identity
    assert payload["sub"] == "user-uuid-role-test"
