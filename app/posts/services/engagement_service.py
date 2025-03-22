from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum
from app.auth.dependencies import get_user_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.redis import RedisManager
from app.posts.services.core_post_service import EnhancedCorePostService, PostCache, PostValidator
import logging
from app.db.mongodb import get_mongodb



logger = logging.getLogger(__name__)

class InteractionType(Enum):
    VIEW = "view"
    LIKE = "like"
    SHARE = "share"
    COMMENT = "comment"

class PostEngagementService:
    def __init__(self, db: AsyncSession):
        self.mongodb = get_mongodb()
        self.engagements = self.mongodb.get_collection("post_engagements")
        self.interaction_history = self.mongodb.get_collection("interaction_history")
        self.db = db  # PostgreSQL session

    async def validate_post_and_user(self, post_id: int, user_id: int) -> bool:
        """Validate that both post and user exist in PostgreSQL"""
        post_service = EnhancedCorePostService()
        post = await post_service.get_post(self.db, post_id)
        user = await get_user_db(self.db, user_id)
        return bool(post and user)

    async def toggle_like(self, post_id: int, user_id: int) -> bool:
        """Toggle like status for a post"""
        # First check if the engagement document exists
        engagement = await self.engagements.find_one({"post_id": post_id})
        
        if engagement and user_id in engagement.get("likes", []):
            # Remove like
            await self.engagements.update_one(
                {"post_id": post_id},
                {
                    "$pull": {"likes": user_id},
                    "$set": {"last_updated": datetime.utcnow()}
                }
            )
            return False
        else:
            # Add like
            await self.engagements.update_one(
                {"post_id": post_id},
                {
                    "$push": {"likes": user_id},
                    "$set": {"last_updated": datetime.utcnow()}
                },
                upsert=True
            )
            # Record interaction in history
            await self.record_interaction(post_id, user_id, InteractionType.LIKE)
            return True

    async def record_interaction(
        self,
        post_id: int,
        user_id: int,
        interaction_type: InteractionType,
        metadata: Optional[Dict] = None
    ):
        """Record an interaction in the history"""
        await self.interaction_history.insert_one({
            "post_id": post_id,
            "user_id": user_id,
            "type": interaction_type.value,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {}
        })

    async def increment_views(self, post_id: int, user_id: int):
        """Increment view count and record unique viewer"""
        await self.engagements.update_one(
            {"post_id": post_id},
            {
                "$inc": {"view_count": 1},
                "$addToSet": {"viewers": user_id},
                "$set": {"last_updated": datetime.utcnow()}
            },
            upsert=True
        )
        await self.record_interaction(post_id, user_id, InteractionType.VIEW)

    async def get_engagement_stats(self, post_id: int) -> Dict:
        """Get engagement statistics for a post"""
        stats = await self.engagements.find_one({"post_id": post_id})
        logger.debug(f"Retrieved stats for post_id {post_id}: {stats}")

        if not stats:
            logger.info(f"No engagement stats found for post_id {post_id}")
            return {
                "likes": 0,
                "views": 0,
                "unique_viewers": 0,
                "last_updated": None
            }
        
        # Ensure stats is a dictionary
        if not isinstance(stats, dict):
            logger.error(f"Unexpected type for stats: {type(stats)}. Expected dict.")
            return {
                "likes": 0,
                "views": 0,
                "unique_viewers": 0,
                "last_updated": None
            }

        likes: List[int] = stats.get("likes", [])
        views: int = stats.get("view_count", 0)
        viewers: List[int] = stats.get("viewers", [])
        last_updated: Any = stats.get("last_updated", None)

        return {
            "likes": len(likes),
            "views": views,
            "unique_viewers": len(viewers),
            "last_updated": last_updated
        }

    async def get_user_engagement(self, user_id: int, post_id: int) -> Dict:
        """Get user's engagement status for a post"""
        stats = await self.engagements.find_one({"post_id": post_id})
        logger.debug(f"Retrieved stats for post_id {post_id}: {stats}")

        if not stats:
            logger.info(f"No engagement stats found for post_id {post_id}")
            return {
                "has_liked": False,
                "has_viewed": False
            }
        
        # Ensure stats is a dictionary
        if not isinstance(stats, dict):
            logger.error(f"Unexpected type for stats: {type(stats)}. Expected dict.")
            return {
                "has_liked": False,
                "has_viewed": False
            }

        likes: List[int] = stats.get("likes", [])
        viewers: List[int] = stats.get("viewers", [])
        
        return {
            "has_liked": user_id in likes,
            "has_viewed": user_id in viewers
        }

    async def get_trending_posts(
        self,
        limit: int = 10,
        hours: int = 24,
        user_id: Optional[int] = None,
        post_id: Optional[int] = None
    ):
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            logger.debug(f"Getting trending posts with user_id: {user_id}, cutoff_time: {cutoff_time}, post_id: {post_id}")
            
            if post_id is not None:
                # Direct query for specific post
                post_data = await self.engagements.find_one({"post_id": post_id})
                if not post_data:
                    logger.warning(f"No post found for post_id: {post_id}")
                    return []
                    
                # Process single post
                post_data = {
                    "post_id": post_data["post_id"],
                    "engagement_score": (
                        len(post_data.get("likes", [])) +
                        (post_data.get("view_count", 0) / 2)
                    ),
                    "unique_viewers": len(post_data.get("viewers", [])),
                    "view_count": post_data.get("view_count", 0),
                    "is_liked": user_id in post_data.get("likes", []),
                    "likes_count": len(post_data.get("likes", [])),
                    "last_updated": post_data.get("last_updated")
                }
                posts_data = [post_data]
                
            else:
                # Regular trending posts query
                pipeline = [
                    {
                        "$match": {
                            "last_updated": {"$gte": cutoff_time}
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "post_id": 1,
                            "likes": 1,
                            "view_count": 1,
                            "viewers": 1,
                            "engagement_score": {
                                "$add": [
                                    {"$size": {"$ifNull": ["$likes", []]}},
                                    {"$divide": [{"$ifNull": ["$view_count", 0]}, 2]}
                                ]
                            },
                            "unique_viewers": {"$size": {"$ifNull": ["$viewers", []]}},
                            "last_updated": 1,
                            "is_liked": {
                                "$cond": [
                                    {"$in": [user_id, {"$ifNull": ["$likes", []]}]},
                                    True,
                                    False
                                ]
                            },
                            "likes_count": {"$size": {"$ifNull": ["$likes", []]}}
                        }
                    },
                    {"$sort": {"engagement_score": -1}},
                    {"$limit": limit}
                ]
                
                posts_data = await self.engagements.aggregate(pipeline).to_list(None)

            if not posts_data:
                return []

            # Initialize services
            redis_manager = RedisManager()
            cache = PostCache(redis_manager=redis_manager)
            validator = PostValidator(redis_manager)
            post_service = EnhancedCorePostService(
                cache=cache,
                validator=validator
            )

            # Get post content from PostgreSQL
            post_ids = [p["post_id"] for p in posts_data]
            posts = {}
            
            async with AsyncSession(self.db.bind) as session:
                for post_id in post_ids:
                    post = await post_service.get_post(session, post_id)
                    if post:
                        posts[post_id] = post
                await session.commit()

            # Combine MongoDB and PostgreSQL data
            enhanced_result = []
            for item in posts_data:
                post_id = item["post_id"]
                if post_id in posts:
                    post_data = posts[post_id]
                    enhanced_result.append({
                        "post_id": post_id,
                        "content": post_data.content,
                        "author_username": post_data.author_username,
                        "created_at": post_data.created_at.isoformat(),
                        "engagement_score": item["engagement_score"],
                        "unique_viewers": item["unique_viewers"],
                        "view_count": item.get("view_count", 0),
                        "likes_count": item["likes_count"],
                        "is_liked": item["is_liked"],
                        "last_updated": item["last_updated"]
                    })
            
            return enhanced_result

        except Exception as e:
            logger.error(f"Error getting trending posts: {e}")
            logger.exception(e)
            return []

    async def get_user_history(
        self,
        user_id: int,
        interaction_type: Optional[InteractionType] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get user's interaction history"""
        match_query = {"user_id": user_id}
        if interaction_type:
            match_query["type"] = interaction_type.value
            
        return await self.interaction_history.find(
            match_query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(None)
    
    async def _debug_mongodb_collection(self):
        """Helper to debug MongoDB collection contents"""
        all_docs = await self.engagements.find().to_list(None)
        logger.debug(f"All MongoDB documents: {all_docs}")
        return all_docs
    
    async def get_batch_engagement_stats(self, post_ids: List[int], user_id: int) -> Dict[str, Dict]:
        """Get engagement statistics for multiple posts in a single query"""
        try:
            # Use MongoDB's $in operator for efficient batch retrieval
            cursor = self.engagements.find({"post_id": {"$in": post_ids}})
            all_stats = await cursor.to_list(length=None)
            
            # Convert to a dictionary keyed by post_id for easy lookup
            stats_by_id = {}
            
            # Process each post's stats
            for stats in all_stats:
                post_id = stats["post_id"]
                likes = stats.get("likes", [])
                viewers = stats.get("viewers", [])
                
                stats_by_id[str(post_id)] = {
                    "likes": len(likes),
                    "views": stats.get("view_count", 0),
                    "unique_viewers": len(viewers),
                    "is_liked": user_id in likes,
                    "last_updated": stats.get("last_updated")
                }
                
            # Add empty stats for any missing posts
            for post_id in post_ids:
                if str(post_id) not in stats_by_id:
                    stats_by_id[str(post_id)] = {
                        "likes": 0,
                        "views": 0,
                        "unique_viewers": 0,
                        "is_liked": False,
                        "last_updated": None
                    }
                    
            return stats_by_id
            
        except Exception as e:
            logger.error(f"Error getting batch engagement stats: {e}")
            # Return empty stats for all requested posts
            return {str(post_id): {
                "likes": 0,
                "views": 0,
                "unique_viewers": 0,
                "is_liked": False,
                "last_updated": None
            } for post_id in post_ids}