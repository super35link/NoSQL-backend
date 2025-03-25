# app/db/mongodb.py
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from functools import lru_cache
from app.core.config import settings

logger = logging.getLogger(__name__)

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
    try:
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
        # Create hashtag_follows collection with indexes
        await db.hashtag_follows.create_index(
            [("user_id", 1), ("hashtag", 1)], 
            unique=True,
            name="user_hashtag_index"
        )
        await db.hashtag_follows.create_index(
            [("user_id", 1)],
            name="follows_by_user"
        )
        await db.hashtag_follows.create_index(
            [("hashtag", 1)],
            name="follows_by_hashtag"
        )

        # Create hashtag_stats collection with indexes
        await db.hashtag_stats.create_index(
            [("tag", 1)],
            unique=True,
            name="hashtag_stats_tag"
        )
        await db.hashtag_stats.create_index(
            [("follower_count", -1)],
            name="popular_hashtags"
        )
        await db.hashtag_stats.create_index(
            [("category", 1), ("follower_count", -1)],
            name="category_popular"
        )

        # Create trending_metrics collection with indexes
        await db.trending_metrics.create_index(
            [("timestamp", -1)],
            name="trending_timeline"
        )
        await db.trending_metrics.create_index(
            [("tag", 1), ("timestamp", -1)],
            name="tag_timeline"
        )
        await db.trending_metrics.create_index(
            [("type", 1), ("tag", 1), ("timestamp", -1)],
            name="interaction_tag_timeline"
        )
        
        logger.info("MongoDB indexes created successfully")
    except Exception as e:
        logger.error("Error creating MongoDB indexes: %s", str(e))