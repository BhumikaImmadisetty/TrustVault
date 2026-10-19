from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    APP_NAME: str = Field(default="TrustVault", description="Application name")
    APP_ENV: Literal["development", "testing", "production"] = Field(
        default="development", description="Application runtime environment"
    )
    
    # repr=False ensures the secret is never shown in repr(), print(), or error traces
    SECRET_KEY: str = Field(
        default="replace-with-a-long-random-secret-before-running",
        repr=False,
        description="Cryptographic secret key for signing JWTs",
    )
    
    MONGODB_URI: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection string URI",
    )
    DATABASE_NAME: str = Field(
        default="trustvault",
        description="MongoDB database name",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        gt=0,
        description="JWT access token expiration time in minutes",
    )
    STORAGE_PATH: str = Field(
        default="storage",
        description="Relative or absolute path for secure private document storage",
    )
    MAX_UPLOAD_SIZE_MB: int = Field(
        default=10,
        gt=0,
        description="Maximum allowed file upload size in megabytes",
    )

    model_config = SettingsConfigDict(
        # Looks for .env in current working directory and in backend/.env
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MAX_UPLOAD_SIZE_MB")
    @classmethod
    def validate_max_upload_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("MAX_UPLOAD_SIZE_MB must be greater than 0")
        return v

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_token_expiry(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0")
        return v

    @property
    def max_upload_size_bytes(self) -> int:
        """Helper property to convert MAX_UPLOAD_SIZE_MB to bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def get_safe_summary(self) -> Dict[str, Any]:
        """
        Return a dictionary of configuration settings with sensitive values masked.
        Safe for logging, debugging, and inspection.
        """
        data = self.model_dump()
        data["SECRET_KEY"] = "***MASKED***"
        # Mask credentials in MONGODB_URI if any exist
        if "@" in self.MONGODB_URI:
            data["MONGODB_URI"] = "mongodb://***:***@" + self.MONGODB_URI.split("@", 1)[1]
        return data


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


# Default singleton instance
settings = get_settings()
