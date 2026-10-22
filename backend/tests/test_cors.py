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


# =========================================================================
# Part C: Environment Variable Settings Source Regression Tests
# =========================================================================

def test_cors_env_var_comma_separated(monkeypatch):
    """Verify Settings parses comma-separated CORS_ORIGINS from environment variables (Render format)."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,https://app.trustvault.example.com",
    )
    settings = Settings()
    assert settings.CORS_ORIGINS == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://app.trustvault.example.com",
    ]


def test_cors_env_var_comma_separated_with_whitespace_and_slashes(monkeypatch):
    """Verify Settings normalizes whitespace and trailing slashes from env var."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "  http://localhost:5173/  ,  https://app.trustvault.example.com/  ",
    )
    settings = Settings()
    assert settings.CORS_ORIGINS == [
        "http://localhost:5173",
        "https://app.trustvault.example.com",
    ]


def test_cors_env_var_json_array(monkeypatch):
    """Verify Settings continues to support JSON-encoded list from environment variables."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["http://localhost:5173", "https://app.trustvault.example.com"]',
    )
    settings = Settings()
    assert settings.CORS_ORIGINS == [
        "http://localhost:5173",
        "https://app.trustvault.example.com",
    ]


def test_cors_env_var_single_origin(monkeypatch):
    """Verify Settings supports a single origin from environment variables."""
    monkeypatch.setenv("CORS_ORIGINS", "https://trustvault.onrender.com")
    settings = Settings()
    assert settings.CORS_ORIGINS == ["https://trustvault.onrender.com"]


def test_cors_env_var_wildcard_rejected(monkeypatch):
    """Verify Settings rejects wildcard in environment variable."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        Settings()


def test_cors_env_var_wildcard_in_json_list_rejected(monkeypatch):
    """Verify Settings rejects wildcard inside JSON list in environment variable."""
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173", "*"]')
    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        Settings()


def test_cors_env_var_invalid_scheme_rejected(monkeypatch):
    """Verify Settings rejects invalid origin scheme from environment variable."""
    monkeypatch.setenv("CORS_ORIGINS", "ftp://evil.com,http://localhost:5173")
    with pytest.raises(ValueError):
        Settings()


def test_cors_env_var_middleware_integration(monkeypatch):
    """Verify CORSMiddleware functions properly when origins are loaded from comma-separated env var."""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://frontend.onrender.com,https://trustvault.example.com",
    )
    env_settings = Settings()

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=env_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @test_app.get("/health")
    def health():
        return {"status": "ok"}

    with TestClient(test_app) as client:
        # Preflight from first allowed origin
        resp1 = client.options(
            "/health",
            headers={
                "Origin": "https://frontend.onrender.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp1.status_code == 200
        assert resp1.headers.get("access-control-allow-origin") == "https://frontend.onrender.com"
        assert resp1.headers.get("access-control-allow-credentials") == "true"

        # Preflight from second allowed origin
        resp2 = client.options(
            "/health",
            headers={
                "Origin": "https://trustvault.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp2.status_code == 200
        assert resp2.headers.get("access-control-allow-origin") == "https://trustvault.example.com"
        assert resp2.headers.get("access-control-allow-credentials") == "true"

        # Untrusted origin
        resp_blocked = client.options(
            "/health",
            headers={
                "Origin": "https://unauthorized-origin.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp_blocked.headers
