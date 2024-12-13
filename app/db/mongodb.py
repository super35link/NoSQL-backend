# app/db/mongodb.py
from motor.motor_asyncio import AsyncIOMotorClient
from functools import lru_cache
from app.core.config import settings

@lru_cache()
def get_mongodb():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    return client[settings.MONGODB_DB_NAME]

# app/core/config.py - add:
class Settings:
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "social_media"
    
# app/db/mongodb.py
async def create_mongodb_indexes():
    db = get_mongodb()
    # Existing indexes
    await db.post_engagements.create_index([("post_id", 1)], unique=True)
    await db.post_engagements.create_index([("post_id", 1), ("last_updated", -1)])
    
    # New indexes for interaction history
    await db.interaction_history.create_index([
        ("post_id", 1),
        ("timestamp", -1)
    ])
    await db.interaction_history.create_index([
        ("user_id", 1),
        ("timestamp", -1)
    ])
    await db.interaction_history.create_index([
        ("type", 1),
        ("timestamp", -1)
    ])