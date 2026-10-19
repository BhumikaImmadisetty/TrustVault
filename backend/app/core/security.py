"""
Security module for TrustVault.
Provides Argon2id password hashing and verification using pwdlib,
and JWT access token creation and verification using PyJWT.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from pwdlib import PasswordHash
from app.core.config import settings

# =========================================================================
# Part A: Password Security (Argon2id)
# =========================================================================

# Initialize recommended PasswordHash instance configured with Argon2id
password_hash = PasswordHash.recommended()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using Argon2id with automatic salt generation.

    Args:
        password: The plaintext password string to hash.

    Returns:
        str: Argon2id hash string ($argon2id$...).

    Raises:
        ValueError: If password is empty, whitespace-only, too short, or exceeds max length.
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty or whitespace-only.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password exceeds maximum length of {MAX_PASSWORD_LENGTH} characters.")

    # Generate salted Argon2id hash
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against an Argon2id hash safely.

    Args:
        plain_password: The plaintext candidate password.
        hashed_password: The Argon2id hash from the database.

    Returns:
        bool: True if password matches the hash, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    # Reject excessively long inputs to prevent CPU exhaustion DoS
    if len(plain_password) > MAX_PASSWORD_LENGTH:
        return False

    try:
        return password_hash.verify(plain_password, hashed_password)
    except Exception:
        # Fails closed on any unexpected error or corrupted hash format
        return False


# =========================================================================
# Part B: JWT Token Security (PyJWT with HS256)
# =========================================================================

ALGORITHM = "HS256"


class TokenSecurityError(Exception):
    """Base exception for all token security and verification errors."""
    pass


class TokenExpiredError(TokenSecurityError):
    """Raised when a token signature has passed its expiration time."""
    pass


class InvalidTokenError(TokenSecurityError):
    """Raised when a token is invalid, malformed, tampered, or missing required claims."""
    pass


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Create a signed JWT access token with subject, issued-at, and expiration claims.

    Args:
        subject: The unique user identifier (e.g., user ID) set as the 'sub' claim.
        expires_delta: Optional custom duration before token expiration.
        additional_claims: Optional non-sensitive metadata to include in the payload.
        secret_key: Optional signing key (defaults to settings.SECRET_KEY).

    Returns:
        str: Encoded and signed JWT string.

    Raises:
        ValueError: If subject is empty or missing.

    Security Note (Requirement 8):
        Claims inside the token payload (such as user roles) are informational only.
        The backend MUST evaluate live account status and current permissions in the
        database on every protected request to enforce instant revocation.
    """
    if not subject or not str(subject).strip():
        raise ValueError("Token subject ('sub') cannot be empty.")

    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {}
    if additional_claims:
        payload.update(additional_claims)

    # Core required claims take precedence
    payload.update({
        "sub": str(subject).strip(),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    })

    signing_key = secret_key or settings.SECRET_KEY
    return jwt.encode(payload, signing_key, algorithm=ALGORITHM)


def decode_access_token(token: str, secret_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Decode, verify signature, and validate claims of a JWT access token.

    Args:
        token: The encoded JWT string.
        secret_key: Optional verification key (defaults to settings.SECRET_KEY).

    Returns:
        Dict[str, Any]: Decoded payload containing verified claims.

    Raises:
        TokenExpiredError: If the token has expired ('exp' claim passed).
        InvalidTokenError: If the token is invalid, tampered, malformed, or missing required claims.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise InvalidTokenError("Token string cannot be empty.")

    signing_key = secret_key or settings.SECRET_KEY

    try:
        payload = jwt.decode(
            token.strip(),
            signing_key,
            algorithms=[ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["sub", "iat", "exp"],
            },
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired.") from exc
    except PyJWTError as exc:
        raise InvalidTokenError(f"Access token validation failed: {exc.__class__.__name__}") from exc
    except Exception as exc:
        raise InvalidTokenError("Access token could not be decoded.") from exc

    sub = payload.get("sub")
    if not sub or not str(sub).strip():
        raise InvalidTokenError("Token 'sub' claim cannot be empty.")

    return payload
