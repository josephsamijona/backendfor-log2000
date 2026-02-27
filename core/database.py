import logging
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

logger = logging.getLogger("core.database")

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_ctx = Database()

async def connect_to_mongo():
    logger.info("Connecting to MongoDB...")
    db_ctx.client = AsyncIOMotorClient(settings.dburl)
    db_ctx.db = db_ctx.client.get_database("locust_dashboard_db")
    # FIX: Verify the connection is actually reachable at startup
    try:
        await db_ctx.client.admin.command("ping")
        logger.info("Connected to MongoDB -> locust_dashboard_db [ping OK]")
    except Exception as e:
        logger.error(f"MongoDB ping FAILED: {e}. L'application démarre mais la base de données est inaccessible.")

def close_mongo_connection():
    if db_ctx.client:
        logger.info("Closing MongoDB connection...")
        db_ctx.client.close()
        logger.info("MongoDB connection closed.")

# Helpers for Dependency Injection
def get_db():
    return db_ctx.db
