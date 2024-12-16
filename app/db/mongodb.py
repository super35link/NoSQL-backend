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

    # Post Engagements Collection Indexes
    await db.post_engagements.create_index(
        [("post_id", 1)], 
        unique=True,
        name="post_engagement_lookup"
    )
    await db.post_engagements.create_index(
        [("post_id", 1), ("last_updated", -1)],
        name="post_engagement_timeline"
    )

    # Interaction History Collection Indexes
    await db.interaction_history.create_index(
        [("post_id", 1), ("timestamp", -1)],
        name="post_interaction_timeline"
    )
    await db.interaction_history.create_index(
        [("user_id", 1), ("timestamp", -1)],
        name="user_interaction_timeline"
    )
    await db.interaction_history.create_index(
        [("type", 1), ("timestamp", -1)],
        name="interaction_type_timeline"
    )

    # Trending Metrics Collection Indexes
    await db.trending_metrics.create_index(
        [("timestamp", -1)],
        name="trending_timeline"
    )
    await db.trending_metrics.create_index(
        [("type", 1), ("tag", 1), ("timestamp", -1)],
        name="trending_tag_lookup"
    )
    await db.trending_metrics.create_index(
        [("category", 1), ("timestamp", -1)],
        name="trending_category_lookup"
    )

    # Topic Classifications Collection Indexes
    await db.topic_classifications.create_index(
        [("post_id", 1)],
        unique=True,
        name="topic_post_lookup"
    )
    await db.topic_classifications.create_index(
        [("topic", 1), ("confidence", -1)],
        name="topic_confidence_lookup"
    )

    # Content Moderation Collection Indexes
    await db.content_moderation.create_index(
        [("content_hash", 1)],
        unique=True,
        name="moderation_content_lookup"
    )
    await db.content_moderation.create_index(
        [("timestamp", -1)],
        name="moderation_timeline"
    )