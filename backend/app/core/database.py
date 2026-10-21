import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from app.core.config import settings

logger = logging.getLogger("trustvault.database")


class DatabaseManager:
    """Manages the MongoDB asynchronous client and database instances."""

    def __init__(self) -> None:
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    def get_client(self) -> AsyncIOMotorClient:
        """
        Return the active MongoDB client, initializing it lazily if not already connected.
        Keeps timeout bounded so connection checks fail fast if the database is unreachable.
        """
        if self.client is None:
            self.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=2000,
            )
            self.db = self.client[settings.DATABASE_NAME]
        return self.client

    def get_database(self) -> AsyncIOMotorDatabase:
        """Return the active MongoDB database instance."""
        if self.db is None:
            self.get_client()
        return self.db

    async def check_connection(self) -> bool:
        """
        Check database connectivity using the MongoDB 'ping' command.
        
        Returns:
            bool: True if ping succeeds, False if unreachable or an error occurs.
            
        Security Note:
            Catches errors safely and never prints or logs raw credentials or connection URIs.
        """
        try:
            database = self.get_database()
            # Send lightweight ping command to admin/primary database
            response = await database.command("ping")
            if (
                isinstance(response, dict)
                and not isinstance(response.get("ok"), bool)
                and response.get("ok") in (1, 1.0)
            ):
                logger.info("MongoDB ping succeeded.")
                return True
            return False
        except ServerSelectionTimeoutError:
            logger.warning("MongoDB ping failed: Server selection timeout (database unreachable).")
            return False
        except PyMongoError as err:
            logger.warning("MongoDB ping failed due to driver error: %s", err.__class__.__name__)
            return False
        except Exception as err:
            logger.error("Unexpected error during MongoDB ping: %s", err.__class__.__name__)
            return False

    async def close_connection(self) -> None:
        """Close the MongoDB client cleanly during application shutdown."""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB client connection closed cleanly.")


# Singleton manager instance
db_manager = DatabaseManager()


def get_db() -> AsyncIOMotorDatabase:
    """Convenience dependency to retrieve the active database instance."""
    return db_manager.get_database()


async def check_db_connection() -> bool:
    """Convenience function to ping and verify database connectivity."""
    return await db_manager.check_connection()


async def close_mongo_connection() -> None:
    """Convenience function to shut down the client."""
    await db_manager.close_connection()


async def init_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Ensure essential MongoDB indexes exist.
    Prevents duplicate permission grants via unique compound index on (document_id, grantee_id).
    Safe and idempotent; raises on failure after logging sanitized error.
    """
    if db is None:
        logger.error("Database index initialization failed: database instance is None")
        raise ValueError("Database instance cannot be None for index initialization")

    try:
        if hasattr(db, "__getitem__"):
            permissions_col = db["permissions"]
            if hasattr(permissions_col, "create_index"):
                await permissions_col.create_index(
                    [("document_id", 1), ("grantee_id", 1)],
                    unique=True,
                    name="uniq_document_grantee",
                )
                await permissions_col.create_index([("grantee_id", 1)], name="idx_grantee")
                await permissions_col.create_index([("document_id", 1)], name="idx_document")
            docs_col = db["documents"]
            if hasattr(docs_col, "create_index"):
                await docs_col.create_index([("owner_id", 1), ("status", 1)], name="idx_owner_status")
            audit_col = db["audit_logs"]
            if hasattr(audit_col, "create_index"):
                await audit_col.create_index([("timestamp", -1)], name="idx_audit_timestamp")
                await audit_col.create_index([("action", 1), ("timestamp", -1)], name="idx_audit_action_time")
                await audit_col.create_index([("actor_id", 1), ("timestamp", -1)], name="idx_audit_actor_time")
                await audit_col.create_index([("document_id", 1), ("timestamp", -1)], name="idx_audit_doc_time")
                await audit_col.create_index([("outcome", 1), ("timestamp", -1)], name="idx_audit_outcome_time")
    except Exception as exc:
        logger.error("Essential database index initialization failed: %s", exc.__class__.__name__)
        raise
