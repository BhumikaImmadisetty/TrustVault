from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal
from urllib.parse import urlsplit
from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class CustomEnvSettingsSource(EnvSettingsSource):
    """Custom environment settings source that prevents premature JSON parsing for CORS_ORIGINS."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        if field_name == "CORS_ORIGINS":
            return value
        return super().decode_complex_value(field_name, field, value)


class CustomDotEnvSettingsSource(DotEnvSettingsSource):
    """Custom .env settings source that prevents premature JSON parsing for CORS_ORIGINS."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        if field_name == "CORS_ORIGINS":
            return value
        return super().decode_complex_value(field_name, field, value)


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
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins for the frontend application",
    )

    model_config = SettingsConfigDict(
        # Looks for .env in current working directory and in backend/.env
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        if isinstance(env_settings, EnvSettingsSource):
            env_settings.__class__ = CustomEnvSettingsSource
        else:
            env_settings = CustomEnvSettingsSource(settings_cls)

        if isinstance(dotenv_settings, DotEnvSettingsSource):
            dotenv_settings.__class__ = CustomDotEnvSettingsSource
        else:
            dotenv_settings = CustomDotEnvSettingsSource(settings_cls)

        return init_settings, env_settings, dotenv_settings, file_secret_settings

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

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: Any) -> List[str]:
        if v is None:
            return ["http://localhost:5173", "http://127.0.0.1:5173"]

        raw_origins: List[str] = []
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("CORS_ORIGINS must contain at least one valid origin.")
            if stripped.startswith("[") and stripped.endswith("]"):
                import json
                try:
                    parsed_json = json.loads(stripped)
                    if isinstance(parsed_json, list):
                        raw_origins = [str(item) for item in parsed_json]
                    else:
                        raw_origins = [stripped]
                except Exception:
                    raw_origins = stripped.split(",")
            else:
                raw_origins = stripped.split(",")
        elif isinstance(v, (list, tuple, set)):
            raw_origins = [str(item) for item in v]
        else:
            raise ValueError(
                f"Invalid CORS_ORIGINS type: {type(v).__name__}. Expected string or list."
            )

        normalized_origins: List[str] = []
        for raw in raw_origins:
            origin = raw.strip()
            if not origin:
                continue

            if origin == "*" or "*" in origin:
                raise ValueError(
                    f"Wildcard CORS origin '{origin}' is not allowed when credentials are enabled."
                )

            parsed = urlsplit(origin)
            if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
                raise ValueError(
                    f"Invalid CORS origin scheme in '{origin}'. Only 'http' and 'https' are permitted."
                )

            if not parsed.netloc:
                raise ValueError(
                    f"Invalid CORS origin '{origin}': missing host or domain."
                )

            if parsed.path and parsed.path != "/":
                raise ValueError(
                    f"Invalid CORS origin '{origin}': origins must not contain a path."
                )

            if parsed.query or parsed.fragment:
                raise ValueError(
                    f"Invalid CORS origin '{origin}': origins must not contain query parameters or fragments."
                )

            if any(char in parsed.netloc for char in (" ", "\t", "\r", "\n", "@")):
                raise ValueError(
                    f"Invalid CORS origin '{origin}': contains illegal characters or user credentials."
                )

            # Avoid trailing-slash mismatch: standard Origin headers do not have a trailing slash
            normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if normalized not in normalized_origins:
                normalized_origins.append(normalized)

        if not normalized_origins:
            raise ValueError("CORS_ORIGINS must contain at least one valid origin.")

        return normalized_origins

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
