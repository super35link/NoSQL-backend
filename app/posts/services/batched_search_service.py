from typing import List, Dict
import asyncio
from datetime import datetime
from collections import deque
import logging
from .embedding_service import PostEmbeddingService

logger = logging.getLogger(__name__)

class BatchedSearchService:
    def __init__(self, batch_size: int = 32, batch_wait_seconds: float = 2.0):
        self.embedding_service = PostEmbeddingService()
        self.batch_size = batch_size
        self.batch_wait = batch_wait_seconds
        self.pending_posts: deque = deque()
        self.processing = False
        self.batch_lock = asyncio.Lock()
        
        # Start the background batch processor
        asyncio.create_task(self._batch_processor())

    async def handle_post_created(self, data: dict):
        """Handle incoming post creation events"""
        async with self.batch_lock:
            self.pending_posts.append(data)
            logger.info(f"Added post {data['post_id']} to batch queue. Queue size: {len(self.pending_posts)}")

    async def _batch_processor(self):
        """Background task to process batches of posts"""
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
        """Process a batch of posts"""
        async with self.batch_lock:
            # Get batch of posts
            batch_size = min(len(self.pending_posts), self.batch_size)
            if batch_size == 0:
                return

            batch = []
            for _ in range(batch_size):
                batch.append(self.pending_posts.popleft())

        try:
            # Prepare batch data
            contents = [post["content"] for post in batch]
            
            # Generate embeddings in batch
            embeddings = await self.embedding_service.generate_embeddings_batch(contents)
            
            # Process results
            for post_data, embedding in zip(batch, embeddings):
                await self.embedding_service.store_embedding(
                    post_id=post_data["post_id"],
                    embedding=embedding,
                    metadata={
                        "author_id": post_data["author_id"],
                        "created_at": post_data["created_at"]
                    }
                )
                
            logger.info(f"Processed batch of {len(batch)} posts")

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            # Return failed posts to queue
            async with self.batch_lock:
                for post in batch:
                    self.pending_posts.appendleft(post)
            raise

    async def process_backlog(self, posts: List[Dict]):
        """Process a backlog of posts"""
        async with self.batch_lock:
            for post in posts:
                self.pending_posts.append(post)
        
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