from typing import List, Dict, Optional
import asyncio
from datetime import datetime, timedelta
from collections import deque
import logging
import hashlib
from app.db.redis import RedisManager
from .embedding_service import PostEmbeddingService

logger = logging.getLogger(__name__)

class BatchSearchService:
    def __init__(
        self, 
        batch_size: int = 32, 
        batch_wait_seconds: float = 2.0,
        embedding_cache_ttl: int = 3600 * 24  # 24 hours for embeddings
    ):
        self.embedding_service = PostEmbeddingService()
        self.redis_manager = RedisManager()
        self.batch_size = batch_size
        self.batch_wait = batch_wait_seconds
        self.embedding_cache_ttl = embedding_cache_ttl
        self.pending_posts: deque = deque()
        self.processing = False
        self.batch_lock = asyncio.Lock()
        
        # Start the background batch processor
        asyncio.create_task(self._batch_processor())

    async def handle_post_created(self, data: dict):
        """Handle incoming post creation events with caching"""
        # Generate cache key based on content
        cache_key = self._generate_cache_key(data["content"])
        
        # Check if embedding already exists in cache
        cached_embedding = await self._get_cached_embedding(cache_key)
        if cached_embedding is not None:
            logger.info(f"Cache hit for post {data['post_id']}")
            await self._store_cached_result(data, cached_embedding)
            return

        # If not in cache, add to batch queue
        async with self.batch_lock:
            self.pending_posts.append((data, cache_key))
            logger.info(f"Added post {data['post_id']} to batch queue. Queue size: {len(self.pending_posts)}")

    async def _batch_processor(self):
        """Background task to process batches of posts with caching"""
        while True:
            try:
                if len(self.pending_posts) >= self.batch_size:
                    await self._process_batch()
                elif len(self.pending_posts) > 0:
                    # Wait for more posts or timeout
                    await asyncio.sleep(self.batch_wait)
                    await self._process_batch()
                else:
                    # No posts to process, wait before checking again
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(1)  # Wait before retrying

    async def _process_batch(self):
        """Process a batch of posts with caching"""
        async with self.batch_lock:
            # Get batch of posts
            batch_size = min(len(self.pending_posts), self.batch_size)
            if batch_size == 0:
                return

            batch = []
            cache_keys = []
            for _ in range(batch_size):
                post_data, cache_key = self.pending_posts.popleft()
                batch.append(post_data)
                cache_keys.append(cache_key)

        try:
            # Prepare batch data
            contents = [post["content"] for post in batch]
            
            # Generate embeddings in batch
            embeddings = await self.embedding_service.generate_embeddings_batch(contents)
            
            # Process results and cache them
            for post_data, embedding, cache_key in zip(batch, embeddings, cache_keys):
                # Cache the embedding
                await self._cache_embedding(cache_key, embedding)
                
                # Store in Qdrant
                await self.embedding_service.store_embedding(
                    post_id=post_data["post_id"],
                    embedding=embedding,
                    metadata={
                        "author_id": post_data["author_id"],
                        "created_at": post_data["created_at"]
                    }
                )
                
            logger.info(f"Processed and cached batch of {len(batch)} posts")

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            # Return failed posts to queue
            async with self.batch_lock:
                for post_data, cache_key in zip(batch, cache_keys):
                    self.pending_posts.appendleft((post_data, cache_key))
            raise

    def _generate_cache_key(self, content: str) -> str:
        """Generate a cache key based on content hash"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        return f"embedding:{content_hash}"

    async def _get_cached_embedding(self, cache_key: str) -> Optional[List[float]]:
        """Get embedding from cache"""
        try:
            cached_data = await self.redis_manager.get_post(cache_key)
            if cached_data:
                return cached_data.get("embedding")
            return None
        except Exception as e:
            logger.error(f"Error getting cached embedding: {e}")
            return None

    async def _cache_embedding(self, cache_key: str, embedding: List[float]):
        """Cache embedding with TTL"""
        try:
            await self.redis_manager.set_post(
                cache_key,
                {
                    "embedding": embedding,
                    "cached_at": datetime.utcnow().isoformat()
                },
                ttl=self.embedding_cache_ttl
            )
        except Exception as e:
            logger.error(f"Error caching embedding: {e}")

    async def _store_cached_result(self, post_data: dict, embedding: List[float]):
        """Store result using cached embedding"""
        try:
            await self.embedding_service.store_embedding(
                post_id=post_data["post_id"],
                embedding=embedding,
                metadata={
                    "author_id": post_data["author_id"],
                    "created_at": post_data["created_at"]
                }
            )
        except Exception as e:
            logger.error(f"Error storing cached result: {e}")
            # Add to queue as fallback
            async with self.batch_lock:
                cache_key = self._generate_cache_key(post_data["content"])
                self.pending_posts.appendleft((post_data, cache_key))

    async def process_backlog(self, posts: List[Dict]):
        """Process a backlog of posts with caching"""
        async with self.batch_lock:
            for post in posts:
                cache_key = self._generate_cache_key(post["content"])
                self.pending_posts.append((post, cache_key))
        
        logger.info(f"Added {len(posts)} posts to backlog")

    async def get_queue_size(self) -> int:
        """Get current size of pending queue"""
        async with self.batch_lock:
            return len(self.pending_posts)

    async def wait_for_empty_queue(self, timeout: float = None):
        """Wait until queue is empty or timeout"""
        start_time = datetime.now()
        while True:
            if await self.get_queue_size() == 0:
                return True
                
            if timeout:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > timeout:
                    return False
                    
            await asyncio.sleep(0.1)

    async def clear_cache(self, older_than_days: int = None):
        """Clear embedding cache with optional age filter"""
        try:
            pattern = "embedding:*"
            if older_than_days:
                cutoff = datetime.utcnow() - timedelta(days=older_than_days)
                # More complex pattern matching would require scanning keys
                
            await self.redis_manager.clear_pattern(pattern)
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")