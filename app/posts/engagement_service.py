from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from app.db.mongodb import get_mongodb

class InteractionType(Enum):
    VIEW = "view"
    LIKE = "like"
    SHARE = "share"
    COMMENT = "comment"

class PostEngagementService:
    def __init__(self):
        self.db = get_mongodb()
        # Using collections from existing MongoDB setup
        self.engagements = self.db.post_engagements
        self.interaction_history = self.db.interaction_history

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
        if not stats:
            return {
                "likes": 0,
                "views": 0,
                "unique_viewers": 0,
                "last_updated": None
            }
        
        return {
            "likes": len(stats.get("likes", [])),
            "views": stats.get("view_count", 0),
            "unique_viewers": len(stats.get("viewers", [])),
            "last_updated": stats.get("last_updated")
        }

    async def get_user_engagement(self, user_id: int, post_id: int) -> Dict:
        """Get user's engagement status for a post"""
        stats = await self.engagements.find_one({"post_id": post_id})
        if not stats:
            return {
                "has_liked": False,
                "has_viewed": False
            }
        
        return {
            "has_liked": user_id in stats.get("likes", []),
            "has_viewed": user_id in stats.get("viewers", [])
        }

    async def get_trending_posts(self, limit: int = 10, hours: int = 24) -> List[Dict]:
        """Get trending posts based on recent engagement"""
        cutoff_time = datetime.utcnow() - datetime.timedelta(hours=hours)
        
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
        
        return await self.engagements.aggregate(pipeline).to_list(None)

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