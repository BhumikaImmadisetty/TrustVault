"""
FastAPI dependency injection providers for database and authentication.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.database import get_db


async def get_database() -> AsyncIOMotorDatabase:
    """
    Dependency provider yielding the active MongoDB database instance.
    Enables clean dependency overriding in automated tests.
    """
    return get_db()
