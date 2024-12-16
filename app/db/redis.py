from redis.asyncio import Redis, ConnectionPool
from typing import Optional, Any, Union, Dict, List
import json
import logging
from functools import wraps
from datetime import datetime, timedelta

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
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True
            )
        self.redis = Redis(connection_pool=self._pool)
        self.post_ttl = settings.REDIS_POST_CACHE_TTL
        self.user_ttl = settings.REDIS_USER_CACHE_TTL
        self.rate_limit_ttl = settings.REDIS_RATE_LIMIT_TTL

    async def close(self):
        """Close Redis connections"""
        await self.redis.close()
        await self._pool.disconnect()

    # Post-related methods
    async def get_post(self, post_id: int) -> Optional[Dict]:
        """Get post from cache"""
        try:
            key = f"post:{post_id}"
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis error getting post {post_id}: {e}")
            return None

    async def set_post(self, post_id: int, post_data: Dict):
        """Cache post data"""
        try:
            key = f"post:{post_id}"
            await self.redis.setex(
                key,
                self.post_ttl,
                json.dumps(post_data)
            )
        except Exception as e:
            logger.error(f"Redis error setting post {post_id}: {e}")

    async def invalidate_post(self, post_id: int):
        """Remove post from cache"""
        try:
            key = f"post:{post_id}"
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis error invalidating post {post_id}: {e}")

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

    async def set_user(self, user_id: int, user_data: Dict):
        """Cache user data"""
        try:
            key = f"user:{user_id}"
            await self.redis.setex(
                key,
                self.user_ttl,
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
                    await pipe.setex(key, ttl, json.dumps(value))
                else:
                    await pipe.set(key, json.dumps(value))
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

    # Context manager support
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

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
                await redis_manager.set_post(cache_key, result)

            return result
        return wrapper
    return decorator

# Global instance
redis_manager = RedisManager()