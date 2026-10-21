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


@pytest.mark.asyncio
async def test_check_connection_integer_one():
    """Verify that check_connection returns True when MongoDB responds with integer 1."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": 1})
    manager.db = mock_db

    result = await manager.check_connection()

    assert result is True


@pytest.mark.asyncio
async def test_check_connection_falsy_or_zero_ok():
    """Verify that check_connection returns False when ok is 0 or 0.0."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    manager.db = mock_db

    for val in (0, 0.0):
        mock_db.command = AsyncMock(return_value={"ok": val})
        assert await manager.check_connection() is False


@pytest.mark.asyncio
async def test_check_connection_rejects_boolean_true():
    """Verify that boolean True for ok is safely rejected (requires int or float 1/1.0)."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": True})
    manager.db = mock_db

    assert await manager.check_connection() is False


@pytest.mark.asyncio
async def test_check_connection_malformed_responses_safe():
    """Verify that None, non-dict, or empty responses return False without throwing AttributeError."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    manager.db = mock_db

    for malformed in (None, {}, {"ok": "string"}, "pong", 123, []):
        mock_db.command = AsyncMock(return_value=malformed)
        assert await manager.check_connection() is False


@pytest.mark.asyncio
async def test_check_connection_unexpected_exception():
    """Verify that unexpected exceptions are caught safely and return False without leaking."""
    manager = DatabaseManager()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=RuntimeError("Unexpected memory error"))
    manager.db = mock_db

    result = await manager.check_connection()

    assert result is False


@pytest.mark.asyncio
async def test_init_indexes_success():
    """Verify that init_indexes creates all essential compound and single indexes."""
    from app.core.database import init_indexes

    mock_db = {}
    mock_permissions = MagicMock()
    mock_permissions.create_index = AsyncMock()
    mock_docs = MagicMock()
    mock_docs.create_index = AsyncMock()
    mock_audit = MagicMock()
    mock_audit.create_index = AsyncMock()

    mock_db["permissions"] = mock_permissions
    mock_db["documents"] = mock_docs
    mock_db["audit_logs"] = mock_audit

    await init_indexes(mock_db)

    # Permissions indexes
    mock_permissions.create_index.assert_any_call(
        [("document_id", 1), ("grantee_id", 1)],
        unique=True,
        name="uniq_document_grantee",
    )
    mock_permissions.create_index.assert_any_call([("grantee_id", 1)], name="idx_grantee")
    mock_permissions.create_index.assert_any_call([("document_id", 1)], name="idx_document")

    # Documents indexes
    mock_docs.create_index.assert_any_call([("owner_id", 1), ("status", 1)], name="idx_owner_status")

    # Audit logs indexes
    mock_audit.create_index.assert_any_call([("timestamp", -1)], name="idx_audit_timestamp")


@pytest.mark.asyncio
async def test_init_indexes_failure_raises_and_does_not_swallow(caplog):
    """Verify that init_indexes raises and logs a sanitized error when index creation fails."""
    import logging
    from app.core.database import init_indexes

    mock_db = {}
    mock_permissions = MagicMock()
    mock_permissions.create_index = AsyncMock(side_effect=PyMongoError("Duplicate key or conflict"))
    mock_db["permissions"] = mock_permissions

    with caplog.at_level(logging.ERROR):
        with pytest.raises(PyMongoError):
            await init_indexes(mock_db)

    assert "Essential database index initialization failed: PyMongoError" in caplog.text


@pytest.mark.asyncio
async def test_init_indexes_none_db_raises_value_error():
    """Verify that calling init_indexes with None raises ValueError."""
    from app.core.database import init_indexes

    with pytest.raises(ValueError, match="Database instance cannot be None"):
        await init_indexes(None)


@pytest.mark.asyncio
async def test_lifespan_logs_sanitized_error_on_index_failure_and_continues(caplog):
    """
    Verify that application lifespan logs sanitized error when index initialization fails,
    does not crash startup, and cleanly shuts down database on exit.
    """
    import logging
    from unittest.mock import patch
    from app.main import app, lifespan

    with caplog.at_level(logging.ERROR):
        with patch("app.main.init_indexes", new=AsyncMock(side_effect=PyMongoError("Atlas network failure"))):
            with patch("app.main.close_mongo_connection", new=AsyncMock()) as mock_close:
                async with lifespan(app):
                    pass
                mock_close.assert_awaited_once()

    assert "Essential database index initialization failed during application startup: PyMongoError" in caplog.text
