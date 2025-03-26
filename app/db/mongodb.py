# app/db/mongodb.py
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from functools import lru_cache
from typing import Dict, Any, Optional, Union, cast
from pymongo import ASCENDING, DESCENDING, TEXT
from app.core.config import settings
from bson import ObjectId

logger = logging.getLogger(__name__)

@lru_cache()
def get_mongodb() -> AsyncIOMotorDatabase:
    """
    Get MongoDB database connection with proper typing.
    Uses LRU cache to reuse the same connection.
    
    Returns:
        AsyncIOMotorDatabase: MongoDB database connection
    """
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    return cast(AsyncIOMotorDatabase, client[settings.MONGODB_DB_NAME])

# Helper functions for safer MongoDB operations
def ensure_object_id(id_value: Union[str, ObjectId]) -> Optional[ObjectId]:
    """
    Convert string ID to ObjectId or return the existing ObjectId.
    Returns None if conversion fails.
    """
    if isinstance(id_value, ObjectId):
        return id_value
        
    if not id_value:
        return None
        
    try:
        return ObjectId(id_value)
    except Exception as e:
        logger.error(f"Invalid ObjectId format: {e}")
        return None

def stringify_object_id(doc: Dict[str, Any], id_field: str = "_id") -> Dict[str, Any]:
    """Convert ObjectId to string in a document for the specified field."""
    if not doc:
        return doc
        
    result = doc.copy()
    if id_field in result and isinstance(result[id_field], ObjectId):
        result[id_field] = str(result[id_field])
    
    return result

# MongoDB indexes creation
async def create_mongodb_indexes() -> None:
    """
    Create all necessary MongoDB indexes for the application.
    This function should be called during application startup.
    """
    db = get_mongodb()
    try:
        logger.info("Creating MongoDB indexes...")
        
        # Create indexes for all collections
        await _create_posts_indexes(db)
        await _create_engagement_indexes(db)
        await _create_interaction_indexes(db)
        await _create_classification_indexes(db)
        await _create_hashtag_indexes(db)
        await _create_moderation_indexes(db)
        await _create_cache_indexes(db)
        
        logger.info("MongoDB indexes created successfully")
    except Exception as e:
        logger.error("Error creating MongoDB indexes: %s", str(e))
        # Don't raise the exception to allow the application to start

async def _create_posts_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for the posts collection"""
    posts = db["posts"]
    
    # Single field indexes
    await posts.create_index("author_id", background=True)
    await posts.create_index("created_at", background=True)
    await posts.create_index("reply_to_id", background=True, sparse=True)
    await posts.create_index("hashtags", background=True)
    
    # Text index for full-text search
    await posts.create_index([("content", TEXT)], 
                            background=True, 
                            default_language="english",
                            weights={"content": 10, "hashtags": 5})
    
    # Compound indexes for common query patterns
    await posts.create_index([("author_id", ASCENDING), ("created_at", DESCENDING)], 
                            background=True)
    await posts.create_index([("is_deleted", ASCENDING), ("is_hidden", ASCENDING)], 
                            background=True)
    await posts.create_index([("thread_id", ASCENDING), ("position_in_thread", ASCENDING)], 
                            background=True, sparse=True)

async def _create_engagement_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for the post_engagements collection"""
    engagements = db["post_engagements"]
    
    # Primary lookup index
    await engagements.create_index([("post_id", ASCENDING)], 
                                 unique=True, 
                                 background=True,
                                 name="post_engagement_lookup")
    
    # Chronological sorting
    await engagements.create_index([("post_id", ASCENDING), ("last_updated", DESCENDING)],
                                 background=True,
                                 name="post_engagement_timeline")
    
    # Sorting and trending indexes
    await engagements.create_index([("engagement_score", DESCENDING), ("last_updated", DESCENDING)], 
                                 background=True)
    await engagements.create_index([("likes_count", DESCENDING), ("post_id", ASCENDING)], 
                                 background=True)
    await engagements.create_index([("views_count", DESCENDING), ("post_id", ASCENDING)], 
                                 background=True)

async def _create_interaction_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for interaction-related collections"""
    # Post interactions collection
    interactions = db["post_interactions"]
    
    # User-specific interaction lookup
    await interactions.create_index([("user_id", ASCENDING), ("post_id", ASCENDING), 
                                  ("interaction_type", ASCENDING)], 
                                 unique=True, background=True)
    
    # Post interaction analytics
    await interactions.create_index([("post_id", ASCENDING), ("interaction_type", ASCENDING), 
                                  ("timestamp", DESCENDING)], 
                                 background=True)
    
    # User activity timeline
    await interactions.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)], 
                                 background=True)
    
    # Timestamp for chronological sorting
    await interactions.create_index("timestamp", background=True)
    
    # Interaction history collection
    interaction_history = db["interaction_history"]
    
    await interaction_history.create_index([("post_id", ASCENDING), ("timestamp", DESCENDING)],
                                         background=True,
                                         name="post_interaction_timeline")
    
    await interaction_history.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)],
                                         background=True,
                                         name="user_interaction_timeline")
    
    await interaction_history.create_index([("type", ASCENDING), ("timestamp", DESCENDING)],
                                         background=True,
                                         name="interaction_type_timeline")

async def _create_classification_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for content classification collections"""
    # Post classifications collection
    classifications = db["post_classifications"]
    
    # Primary lookup index
    await classifications.create_index("post_id", unique=True, background=True)
    
    # Topic-based search
    await classifications.create_index([("topics.topic", ASCENDING), ("topics.confidence", DESCENDING)], 
                                     background=True)
    
    # Sentiment analysis
    await classifications.create_index([("sentiment.positive", DESCENDING), ("created_at", DESCENDING)], 
                                     background=True, sparse=True)
    await classifications.create_index([("sentiment.negative", DESCENDING), ("created_at", DESCENDING)], 
                                     background=True, sparse=True)
    
    # Topic classifications collection from the original implementation
    topic_classifications = db["topic_classifications"]
    
    await topic_classifications.create_index([("post_id", ASCENDING)],
                                          unique=True,
                                          background=True,
                                          name="topic_post_lookup")
    
    await topic_classifications.create_index([("topic", ASCENDING), ("confidence", DESCENDING)],
                                          background=True,
                                          name="topic_confidence_lookup")

async def _create_hashtag_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for hashtag-related collections"""
    # Hashtag statistics
    hashtag_stats = db["hashtag_stats"]
    
    await hashtag_stats.create_index([("tag", ASCENDING)],
                                   unique=True,
                                   background=True,
                                   name="hashtag_stats_tag")
    
    await hashtag_stats.create_index([("follower_count", DESCENDING)],
                                   background=True,
                                   name="popular_hashtags")
    
    await hashtag_stats.create_index([("category", ASCENDING), ("follower_count", DESCENDING)],
                                   background=True,
                                   name="category_popular")
    
    # Hashtag follows
    hashtag_follows = db["hashtag_follows"]
    
    await hashtag_follows.create_index([("user_id", ASCENDING), ("hashtag", ASCENDING)],
                                     unique=True,
                                     background=True,
                                     name="user_hashtag_index")
    
    await hashtag_follows.create_index([("user_id", ASCENDING)],
                                     background=True,
                                     name="follows_by_user")
    
    await hashtag_follows.create_index([("hashtag", ASCENDING)],
                                     background=True,
                                     name="follows_by_hashtag")
    
    # Trending metrics
    trending_metrics = db["trending_metrics"]
    
    await trending_metrics.create_index([("timestamp", DESCENDING)],
                                      background=True,
                                      name="trending_timeline")
    
    await trending_metrics.create_index([("tag", ASCENDING), ("timestamp", DESCENDING)],
                                      background=True,
                                      name="tag_timeline")
    
    await trending_metrics.create_index([("type", ASCENDING), ("tag", ASCENDING), ("timestamp", DESCENDING)],
                                      background=True,
                                      name="interaction_tag_timeline")
    
    await trending_metrics.create_index([("category", ASCENDING), ("timestamp", DESCENDING)],
                                      background=True,
                                      name="trending_category_lookup")

async def _create_moderation_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for content moderation"""
    moderation = db["content_moderation"]
    
    await moderation.create_index([("content_hash", ASCENDING)],
                                unique=True,
                                background=True,
                                name="moderation_content_lookup")
    
    await moderation.create_index([("timestamp", DESCENDING)],
                                background=True,
                                name="moderation_timeline")

async def _create_cache_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create TTL indexes for cache collections"""
    # User cache collection
    user_cache = db["user_cache"]
    
    # Primary lookup index
    await user_cache.create_index("user_id", unique=True, background=True)
    
    # Username lookup
    await user_cache.create_index("username", unique=True, background=True)
    
    # TTL index
    await user_cache.create_index("cached_at", expireAfterSeconds=3600, background=True)
    
    # Post cache
    post_cache = db["post_cache"]
    await post_cache.create_index("created_at", expireAfterSeconds=3600, background=True)
    await post_cache.create_index("post_id", background=True)
    
    # Rate limiting
    rate_limit = db["rate_limit"]
    await rate_limit.create_index("created_at", expireAfterSeconds=900, background=True)  # 15 minutes
    await rate_limit.create_index([("user_id", ASCENDING), ("endpoint", ASCENDING)], 
                                background=True)
    
    # Interaction cache
    interaction_cache = db["interaction_cache"]
    await interaction_cache.create_index("created_at", expireAfterSeconds=3600, background=True)