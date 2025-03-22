from datetime import datetime
from redis.asyncio import Redis, ConnectionPool
from typing import Optional, Any, Dict, List
import json
import logging
import asyncio
from functools import wraps
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import async_session_maker
from app.db.models import Post

from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                url=settings.REDIS_URL,
                password=None,
                db=settings.REDIS_DB,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True
            )
        self.redis = Redis(connection_pool=self._pool)
        self.post_ttl = settings.REDIS_POST_CACHE_TTL
        self.user_ttl = settings.REDIS_USER_CACHE_TTL
        self.rate_limit_ttl = settings.REDIS_RATE_LIMIT_TTL
        
        # Interaction settings
        self.interaction_ttl = 3600  # 1 hour for interaction counters
        self.flush_threshold = 10    # Flush to DB after 10 interactions
        self.flush_interval = 300    # Flush all counters every 5 minutes

    async def close(self):
        """Close Redis connections"""
        await self.redis.close()
        await self._pool.disconnect()

    # Post-related methods
    async def scan_keys(self, pattern: str, count: int = 1000) -> List[str]:
        """Scan Redis keys matching a pattern"""
        try:
            keys = []
            async for key in self.redis.iscan(match=pattern, count=count):
                keys.append(key)
            return keys
        except Exception as e:
            logger.error(f"Redis scan error for pattern {pattern}: {e}")
            return []

    async def get_post(self, post_id: int) -> Optional[Dict]:
        """Get post from cache"""
        try:
            key = f"post:{post_id}"
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis error getting post {post_id}: {e}")
            return None

    async def set_post(self, post_id: int, post_data: Dict, ttl: Optional[int] = None):
        """Cache post data with optional TTL"""
        try:
            key = f"post:{post_id}"
            
            logger.debug(f"Caching post {post_id} with TTL {ttl or self.post_ttl}")

            # Use provided TTL or fall back to default
            expire_time = ttl if ttl is not None else self.post_ttl
            await self.redis.setex(
                key,
                expire_time,
                json.dumps(post_data, cls=DateTimeJSONEncoder)  # Use the custom encoder
            )
            logger.debug(f"Successfully cached post {post_id}")
        except Exception as e:
            logger.error(f"Redis error setting post {post_id}: {e}")


    async def invalidate_post(self, post_id: int):
        """Remove post from cache"""
        try:
            key = f"post:{post_id}"
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis error invalidating post {post_id}: {e}")

    # Interaction methods
    async def increment_interaction(self, post_id: int, interaction_type: str, user_id: Optional[int] = None) -> int:
        """Increment interaction counter in Redis and track user interaction"""
        try:
            # Interaction counter key
            counter_key = f"interaction:{interaction_type}:{post_id}"
            
            # Track user interaction if user_id is provided
            if user_id is not None:
                user_key = f"user:{user_id}:{interaction_type}:{post_id}"
                # Check if user already performed this interaction
                exists = await self.redis.exists(user_key)
                if exists:
                    # User already performed this interaction, don't increment counter
                    return await self.redis.get(counter_key) or 0
                
                # Mark that user performed this interaction
                await self.redis.set(user_key, 1, ex=self.interaction_ttl)
            
            # Increment the counter
            count = await self.redis.incr(counter_key)
            
            # Set expiry if this is a new key
            if count == 1:
                await self.redis.expire(counter_key, self.interaction_ttl)
                
            # If count reaches threshold, trigger flush to database
            if count % self.flush_threshold == 0:
                await self.flush_interaction(post_id, interaction_type)
                
            return count
        except Exception as e:
            logger.error(f"Redis error incrementing {interaction_type} for post {post_id}: {e}")
            return 0

    async def remove_interaction(self, post_id: int, interaction_type: str, user_id: int) -> int:
        """Remove user interaction and decrement counter"""
        try:
            # User interaction key
            user_key = f"user:{user_id}:{interaction_type}:{post_id}"
            
            # Check if user performed this interaction
            exists = await self.redis.exists(user_key)
            if not exists:
                # User did not perform this interaction
                return await self.redis.get(f"interaction:{interaction_type}:{post_id}") or 0
            
            # Remove user interaction
            await self.redis.delete(user_key)
            
            # Decrement the counter
            counter_key = f"interaction:{interaction_type}:{post_id}"
            count = await self.redis.decr(counter_key)
            
            # If count becomes non-positive, set to 0
            if count < 0:
                await self.redis.set(counter_key, 0)
                count = 0
                
            # If count reaches threshold, trigger flush to database
            if count % self.flush_threshold == 0:
                await self.flush_interaction(post_id, interaction_type)
                
            return count
        except Exception as e:
            logger.error(f"Redis error removing {interaction_type} for post {post_id}: {e}")
            return 0

    async def check_user_interaction(self, post_id: int, interaction_type: str, user_id: int) -> bool:
        """Check if a user has performed a specific interaction with a post"""
        try:
            user_key = f"user:{user_id}:{interaction_type}:{post_id}"
            return bool(await self.redis.exists(user_key))
        except Exception as e:
            logger.error(f"Redis error checking user interaction: {e}")
            return False

    async def flush_interaction(self, post_id: int, interaction_type: str):
        """Flush interaction count to PostgreSQL"""
        try:
            key = f"interaction:{interaction_type}:{post_id}"
            count = int(await self.redis.get(key) or 0)
            
            if count > 0:
                # Update the database
                async with async_session_maker() as session:
                    await self._update_post_interaction(session, post_id, interaction_type, count)
                    await session.commit()
                
                # Reset counter in Redis after successful database update
                await self.redis.set(key, 0)
                logger.info(f"Flushed {count} {interaction_type} interactions for post {post_id}")
            
        except Exception as e:
            logger.error(f"Error flushing {interaction_type} for post {post_id}: {e}")

    async def _update_post_interaction(self, session: AsyncSession, post_id: int, interaction_type: str, count: int):
        """Update post interaction count in PostgreSQL"""
        try:
            # Create appropriate update statement based on interaction type
            if interaction_type == "like":
                stmt = update(Post).where(Post.id == post_id).values(like_count=Post.like_count + count)
            elif interaction_type == "view":
                stmt = update(Post).where(Post.id == post_id).values(view_count=Post.view_count + count)
            elif interaction_type == "repost":
                stmt = update(Post).where(Post.id == post_id).values(repost_count=Post.repost_count + count)
            else:
                logger.warning(f"Unknown interaction type: {interaction_type}")
                return
                
            # Execute the update
            await session.execute(stmt)
            
        except Exception as e:
            logger.error(f"Database error updating {interaction_type} for post {post_id}: {e}")
            raise

    async def start_periodic_flush(self):
        """Start periodic flush of all interaction counters"""
        while True:
            try:
                # Get all interaction keys
                keys = await self.redis.keys("interaction:*")
                
                for key in keys:
                    parts = key.split(":")
                    if len(parts) == 3:
                        interaction_type = parts[1]
                        post_id = int(parts[2])
                        await self.flush_interaction(post_id, interaction_type)
                        
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")
                
            # Wait before next flush cycle
            await asyncio.sleep(self.flush_interval)

    # User-related methods
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user from cache"""
        try:
            key = f"user:{user_id}"
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis error getting user {user_id}: {e}")
            return None

    async def set_user(self, user_id: int, user_data: Dict, ttl: Optional[int] = None):
        """Cache user data with optional TTL"""
        try:
            key = f"user:{user_id}"
            # Use provided TTL or fall back to default
            expire_time = ttl if ttl is not None else self.user_ttl
            await self.redis.setex(
                key,
                expire_time,
                json.dumps(user_data)
            )
        except Exception as e:
            logger.error(f"Redis error setting user {user_id}: {e}")

    # Rate limiting methods
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> bool:
        """Check rate limit for a key"""
        try:
            current = await self.redis.get(key)
            if current is None:
                pipe = self.redis.pipeline()
                await pipe.setex(key, window_seconds, 1)
                await pipe.execute()
                return True
            elif int(current) >= limit:
                return False
            else:
                await self.redis.incr(key)
                return True
        except Exception as e:
            logger.error(f"Redis rate limit error for {key}: {e}")
            return True  # Fail open on errors

    # Counter methods
    async def increment_counter(
        self,
        key: str,
        amount: int = 1,
        ttl: Optional[int] = None
    ) -> int:
        """Increment a counter with optional TTL"""
        try:
            pipe = self.redis.pipeline()
            await pipe.incr(key, amount)
            if ttl:
                await pipe.expire(key, ttl)
            results = await pipe.execute()
            return results[0]
        except Exception as e:
            logger.error(f"Redis counter error for {key}: {e}")
            return 0

    async def get_counter(self, key: str) -> int:
        """Get counter value"""
        try:
            value = await self.redis.get(key)
            return int(value) if value else 0
        except Exception as e:
            logger.error(f"Redis get counter error for {key}: {e}")
            return 0

    # Batch operations
    async def bulk_get(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys at once"""
        try:
            pipe = self.redis.pipeline()
            for key in keys:
                await pipe.get(key)
            values = await pipe.execute()
            return {
                key: json.loads(value) if value else None
                for key, value in zip(keys, values)
            }
        except Exception as e:
            logger.error(f"Redis bulk get error: {e}")
            return {}

    async def bulk_set(
        self,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ):
        """Set multiple key-value pairs"""
        try:
            pipe = self.redis.pipeline()
            for key, value in data.items():
                if ttl:
                    await pipe.setex(key, ttl, json.dumps(value, cls=DateTimeJSONEncoder))
                else:
                    await pipe.set(key, json.dumps(value, cls=DateTimeJSONEncoder))
            await pipe.execute()
        except Exception as e:
            logger.error(f"Redis bulk set error: {e}")

    # Utility methods
    async def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern"""
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
        except Exception as e:
            logger.error(f"Redis clear pattern error for {pattern}: {e}")

    async def health_check(self) -> bool:
        """Check if Redis is operational"""
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    async def delete_key(self, key: str):
        """Delete a key from Redis."""
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Error deleting key: {e}")

    # Context manager support
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
class DateTimeJSONEncoder(json.JSONEncoder):
    """JSON encoder that can handle datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Cache decorator
def redis_cache(prefix: str, ttl: int = 3600):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            redis_manager = RedisManager()
            
            # Create cache key
            key_parts = [prefix]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # Try to get from cache
            cached = await redis_manager.get_post(cache_key)
            if cached is not None:
                return cached

            # If not in cache, execute function
            result = await func(*args, **kwargs)

            # Cache the result
            if result is not None:
                await redis_manager.set_post(cache_key, result, ttl=ttl)

            return result
        return wrapper
    return decorator

# Global instance
redis_manager = RedisManager()