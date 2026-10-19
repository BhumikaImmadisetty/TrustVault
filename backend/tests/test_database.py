"""
Automated unit tests for the MongoDB database module using mocks.
Verifies ping logic, error handling, and connection cleanup without requiring a live MongoDB server.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from app.core.database import DatabaseManager


@pytest.mark.asyncio
async def test_check_connection_success():
    """Verify that check_connection returns True when MongoDB responds to ping."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": 1.0})
    manager.db = mock_db

    result = await manager.check_connection()

    assert result is True
    mock_db.command.assert_awaited_once_with("ping")


@pytest.mark.asyncio
async def test_check_connection_timeout_failure():
    """Verify that check_connection safely returns False on ServerSelectionTimeoutError without raising."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=ServerSelectionTimeoutError("Server unreachable"))
    manager.db = mock_db

    result = await manager.check_connection()

    assert result is False


@pytest.mark.asyncio
async def test_check_connection_driver_error():
    """Verify that check_connection safely returns False on PyMongoError without raising."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=PyMongoError("Driver network error"))
    manager.db = mock_db

    result = await manager.check_connection()

    assert result is False


@pytest.mark.asyncio
async def test_close_connection_cleans_up():
    """Verify that close_connection closes the client and resets state to None."""
    manager = DatabaseManager()
    mock_client = MagicMock()
    manager.client = mock_client
    manager.db = MagicMock()

    await manager.close_connection()

    mock_client.close.assert_called_once()
    assert manager.client is None
    assert manager.db is None
