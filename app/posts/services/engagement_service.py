from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum
from app.auth.dependencies import get_user_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.posts.services.core_post_service import EnhancedCorePostService
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

    async def get_trending_posts(self, limit: int = 10, hours: int = 24) -> List[Dict]:
        """Get trending posts based on recent engagement"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        logger.debug(f"Cutoff time: {cutoff_time}")

        pipeline = [
            {"$match": {"last_updated": {"$gte": cutoff_time}}},
            {"$project": {
                "post_id": 1,
                "engagement_score": {
                    "$add": [
                        {"$size": {"$ifNull": ["$likes", []]}},
                        {"$divide": [{"$ifNull": ["$view_count", 0]}, 2]}
                    ]
                },
                "unique_viewers": {"$size": {"$ifNull": ["$viewers", []]}},
                "last_updated": 1
            }},
            {"$sort": {"engagement_score": -1}},
            {"$limit": limit}
        ]
        
        try:
            result = await self.engagements.aggregate(pipeline).to_list(None)
            logger.debug(f"Aggregation result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error in aggregation pipeline: {e}")
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