"""
Automated tests for the /health endpoint.
Validates healthy and unhealthy service responses, status codes, and non-exposure of sensitive details.
"""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings


def test_health_check_healthy():
    """Verify that GET /health returns HTTP 200 with connected database status when MongoDB ping succeeds."""
    with patch("app.main.check_db_connection", new=AsyncMock(return_value=True)):
        with TestClient(app) as client:
            response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["app"] == settings.APP_NAME
    assert data["env"] == settings.APP_ENV


def test_health_check_unhealthy_when_database_down():
    """Verify that GET /health returns HTTP 503 when MongoDB is unreachable or ping fails."""
    with patch("app.main.check_db_connection", new=AsyncMock(return_value=False)):
        with TestClient(app) as client:
            response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"
    assert data["app"] == settings.APP_NAME
    assert data["env"] == settings.APP_ENV


def test_health_check_unhealthy_when_database_probe_raises():
    """Verify that GET /health catches probe errors, returns HTTP 503, and sanitizes output."""
    with patch("app.main.check_db_connection", new=AsyncMock(side_effect=RuntimeError("Database crashed"))):
        with TestClient(app) as client:
            response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"


def test_health_check_never_leaks_sensitive_information():
    """Verify that /health responses never expose credentials, connection strings, or stack traces."""
    with patch("app.main.check_db_connection", new=AsyncMock(return_value=False)):
        with TestClient(app) as client:
            response = client.get("/health")

    raw_text = response.text
    # Sensitive items that must never appear in health check output
    assert "password" not in raw_text.lower()
    assert "secret" not in raw_text.lower()
    assert "mongodb://" not in raw_text
    assert "mongodb+srv://" not in raw_text
    assert "@" not in raw_text
    assert "traceback" not in raw_text.lower()
