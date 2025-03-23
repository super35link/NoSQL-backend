# New MongoDB-based caching manager (replaces RedisManager)
import asyncio
from datetime import datetime
from app import settings
from motor.motor_asyncio import AsyncIOMotorClient



class MongoDBCacheManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Connect to MongoDB with in-memory storage engine for cache collection
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DB]
        
        # Create cache collections with TTL indexes
        self.post_cache = self.db["post_cache"]
        self.user_cache = self.db["user_cache"]
        self.rate_limit = self.db["rate_limit"]
        self.interaction_cache = self.db["interaction_cache"]
        
        # Setup TTL indexes for automatic expiration
        asyncio.create_task(self._setup_indexes())
    
    async def _setup_indexes(self):
        # Create TTL indexes for cache collections
        await self.post_cache.create_index("created_at", expireAfterSeconds=settings.POST_CACHE_TTL)
        await self.user_cache.create_index("created_at", expireAfterSeconds=settings.USER_CACHE_TTL)
        await self.rate_limit.create_index("created_at", expireAfterSeconds=settings.RATE_LIMIT_TTL)
        await self.interaction_cache.create_index("created_at", expireAfterSeconds=3600)  # 1 hour
        
        # Create additional indexes for performance
        await self.post_cache.create_index("post_id")
        await self.user_cache.create_index("user_id")
        await self.interaction_cache.create_index([("post_id", 1), ("interaction_type", 1)])
        await self.interaction_cache.create_index([("user_id", 1), ("interaction_type", 1), ("post_id", 1)])
    
    # Post caching methods
    async def get_post(self, post_id: int):
        result = await self.post_cache.find_one({"post_id": post_id})
        return result["data"] if result else None
    
    async def set_post(self, post_id: int, post_data: dict):
        await self.post_cache.update_one(
            {"post_id": post_id},
            {"$set": {
                "post_id": post_id,
                "data": post_data,
                "created_at": datetime.utcnow()
            }},
            upsert=True
        )
    
    async def invalidate_post(self, post_id: int):
        await self.post_cache.delete_one({"post_id": post_id})
    
    # Interaction methods
    async def increment_interaction(self, post_id: int, interaction_type: str, user_id: int = None):
        # Check if user already performed this interaction
        if user_id:
            user_interaction = await self.interaction_cache.find_one({
                "user_id": user_id,
                "post_id": post_id,
                "interaction_type": interaction_type
            })
            
            if user_interaction:
                return user_interaction["count"]
            
            # Mark user interaction
            await self.interaction_cache.insert_one({
                "user_id": user_id,
                "post_id": post_id,
                "interaction_type": interaction_type,
                "created_at": datetime.utcnow()
            })
        
        # Increment counter
        result = await self.interaction_cache.update_one(
            {"post_id": post_id, "interaction_type": interaction_type, "counter": True},
            {"$inc": {"count": 1}, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
        
        # Get updated count
        counter = await self.interaction_cache.find_one(
            {"post_id": post_id, "interaction_type": interaction_type, "counter": True}
        )
        count = counter["count"] if counter else 1
        
        # If count reaches threshold, flush to MongoDB engagement collection
        if count % 10 == 0:  # Flush threshold
            await self.flush_interaction(post_id, interaction_type)
            
        return count
    
    async def flush_interaction(self, post_id: int, interaction_type: str):
        # Get current count
        counter = await self.interaction_cache.find_one(
            {"post_id": post_id, "interaction_type": interaction_type, "counter": True}
        )
        
        if not counter or counter["count"] <= 0:
            return
            
        count = counter["count"]
        
        # Update engagement in MongoDB instead of PostgreSQL
        await self.db.post_engagements.update_one(
            {"post_id": post_id},
            {"$inc": {f"{interaction_type}_count": count}},
            upsert=True
        )
        
        # Reset counter
        await self.interaction_cache.update_one(
            {"post_id": post_id, "interaction_type": interaction_type, "counter": True},
            {"$set": {"count": 0}}
        )
