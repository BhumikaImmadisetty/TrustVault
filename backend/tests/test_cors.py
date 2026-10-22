"""
Automated unit and integration tests for TrustVault CORS configuration and middleware behavior.
Validates origin parsing, whitespace/trailing-slash normalization, wildcard rejection,
malformed origin handling, and preflight response headers.
"""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import app


# =========================================================================
# Part A: Settings CORS_ORIGINS Validation Tests
# =========================================================================

def test_cors_default_origins_allowed():
    """Verify that both local development origins are configured by default."""
    settings = Settings()
    assert "http://localhost:5173" in settings.CORS_ORIGINS
    assert "http://127.0.0.1:5173" in settings.CORS_ORIGINS
    assert len(settings.CORS_ORIGINS) == 2


def test_cors_configured_production_origin_accepted():
    """Verify that a single configured production origin is accepted and normalized."""
    settings = Settings(CORS_ORIGINS="https://app.trustvault.example.com")
    assert settings.CORS_ORIGINS == ["https://app.trustvault.example.com"]


def test_cors_multiple_comma_separated_origins():
    """Verify that multiple comma-separated origins from the environment are parsed and preserved."""
    origins_str = "http://localhost:5173, http://127.0.0.1:5173, https://app.trustvault.com"
    settings = Settings(CORS_ORIGINS=origins_str)
    assert settings.CORS_ORIGINS == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://app.trustvault.com",
    ]


def test_cors_whitespace_and_trailing_slash_normalization():
    """Verify that leading/trailing whitespace and trailing slashes are properly normalized."""
    raw = "  https://app.trustvault.com/  ,  http://localhost:5173/  "
    settings = Settings(CORS_ORIGINS=raw)
    assert settings.CORS_ORIGINS == [
        "https://app.trustvault.com",
        "http://localhost:5173",
    ]


def test_cors_deduplication():
    """Verify that duplicate origin definitions are deduplicated cleanly."""
    raw = "http://localhost:5173, http://localhost:5173/, http://localhost:5173"
    settings = Settings(CORS_ORIGINS=raw)
    assert settings.CORS_ORIGINS == ["http://localhost:5173"]


def test_cors_wildcard_rejected():
    """Verify that wildcard origins are strictly rejected to avoid insecure credential handling."""
    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        Settings(CORS_ORIGINS="*")

    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        Settings(CORS_ORIGINS="https://*.trustvault.com")

    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        Settings(CORS_ORIGINS=["http://localhost:5173", "*"])


@pytest.mark.parametrize(
    "malformed",
    [
        "localhost:5173",                     # Missing scheme
        "ftp://example.com",                   # Disallowed scheme
        "javascript:alert(1)",                # Disallowed scheme
        "https://example.com/api",            # Disallowed non-root path
        "https://example.com?key=val",        # Disallowed query parameters
        "https://example.com#section",        # Disallowed fragment
        "https://user:pass@example.com",      # Disallowed credentials / userinfo
        "",                                   # Empty string
        "   ",                                # Whitespace only
        ", , ",                               # Commas only
    ],
)
def test_cors_malformed_origins_rejected(malformed):
    """Verify that malformed or unsafe origin specifications are rejected."""
    with pytest.raises(ValueError):
        Settings(CORS_ORIGINS=malformed)


# =========================================================================
# Part B: Middleware & Preflight Integration Tests
# =========================================================================

def test_cors_local_development_preflight_functional():
    """Verify that existing local development origins successfully complete CORS preflights."""
    with patch("app.main.check_db_connection", new=AsyncMock(return_value=True)):
        with TestClient(app) as client:
            # 1. localhost origin
            resp_lh = client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert resp_lh.status_code == 200
            assert resp_lh.headers.get("access-control-allow-origin") == "http://localhost:5173"
            assert resp_lh.headers.get("access-control-allow-credentials") == "true"

            # 2. 127.0.0.1 origin
            resp_ip = client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert resp_ip.status_code == 200
            assert resp_ip.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
            assert resp_ip.headers.get("access-control-allow-credentials") == "true"


def test_cors_unauthorized_origin_rejected_in_preflight():
    """Verify that unauthorized origins do not receive CORS allow headers."""
    with patch("app.main.check_db_connection", new=AsyncMock(return_value=True)):
        with TestClient(app) as client:
            resp = client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": "https://attacker.evil.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert "access-control-allow-origin" not in resp.headers


def test_cors_production_origin_configured_middleware():
    """Verify that a customized production origin works correctly in CORSMiddleware."""
    custom_settings = Settings(CORS_ORIGINS="https://app.trustvault.example.com")

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=custom_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @test_app.get("/ping")
    def ping():
        return {"ping": "pong"}

    with TestClient(test_app) as client:
        # Preflight from configured production origin
        resp_allowed = client.options(
            "/ping",
            headers={
                "Origin": "https://app.trustvault.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp_allowed.status_code == 200
        assert resp_allowed.headers.get("access-control-allow-origin") == "https://app.trustvault.example.com"
        assert resp_allowed.headers.get("access-control-allow-credentials") == "true"

        # Preflight from untrusted origin
        resp_denied = client.options(
            "/ping",
            headers={
                "Origin": "https://untrusted.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp_denied.headers
