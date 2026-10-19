import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Standard RFC-compliant email regex pattern
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRole(str, Enum):
    """
    Supported application roles in TrustVault.
    - admin: System administration and security audit oversight.
    - owner: Document creator who can manage and share owned documents.
    - viewer: User with read-only/download access to explicitly shared documents.
    """
    ADMIN = "admin"
    OWNER = "owner"
    VIEWER = "viewer"


def validate_and_normalize_email_str(value: str) -> str:
    """Normalize and validate an email string without external dependencies."""
    if not isinstance(value, str):
        raise ValueError("Email must be a string.")
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 254:
        raise ValueError("Email address must be between 1 and 254 characters.")
    if not EMAIL_REGEX.match(normalized):
        raise ValueError("Invalid email address format.")
    return normalized


class UserRegister(BaseModel):
    """
    Public user registration input schema.
    Enforces strong password constraints and prevents self-assignment of the admin role.
    """
    email: str = Field(description="User primary email address")
    full_name: str = Field(min_length=2, max_length=100, description="Full name of user")
    password: str = Field(min_length=8, max_length=128, description="Plaintext password")
    role: Optional[UserRole] = Field(
        default=UserRole.VIEWER,
        description="Assigned role upon registration; defaults to viewer and cannot be admin",
    )

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Strip whitespace, lowercase, and validate email syntax."""
        return validate_and_normalize_email_str(v)

    @field_validator("role")
    @classmethod
    def disallow_admin_role_on_registration(cls, v: Optional[UserRole]) -> UserRole:
        """Security guard: prevent public registration from assigning the admin role."""
        if v == UserRole.ADMIN or (isinstance(v, str) and v.lower() == "admin"):
            raise ValueError("Registration cannot assign the admin role.")
        return v or UserRole.VIEWER

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Ensure password contains uppercase, lowercase, and digit characters."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v) > 128:
            raise ValueError("Password cannot exceed 128 characters.")
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_upper and has_lower and has_digit):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, and one digit."
            )
        return v


class UserResponse(BaseModel):
    """
    Public user representation returned by API endpoints.
    Strictly excludes password hashes and authentication secrets.
    """
    id: str = Field(description="Unique user identifier")
    email: str = Field(description="Normalized email address")
    full_name: str = Field(description="Full name of user")
    role: UserRole = Field(description="User access control role")
    is_active: bool = Field(description="Whether account is active")
    created_at: datetime = Field(description="Account creation timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return validate_and_normalize_email_str(v)


class UserInDB(BaseModel):
    """
    Internal user schema reflecting MongoDB document structure.
    Contains the salted Argon2 password hash.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    full_name: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    hashed_password: str = Field(description="Salted Argon2id password hash")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return validate_and_normalize_email_str(v)


class UserRoleUpdate(BaseModel):
    """Schema for administrative role reassignment."""
    role: UserRole


class UserLogin(BaseModel):
    """User login credential input schema."""
    email: str = Field(description="User primary email address")
    password: str = Field(min_length=1, max_length=128, description="User password")

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return validate_and_normalize_email_str(v)


class TokenResponse(BaseModel):
    """Authentication response payload containing JWT access token and user metadata."""
    access_token: str = Field(description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme type")
    user: UserResponse = Field(description="Public profile of authenticated user")
