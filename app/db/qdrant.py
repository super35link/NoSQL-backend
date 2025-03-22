import hashlib
import json
import logging
from typing import Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.core.config import settings
from app.db.redis import redis_manager  # Use global instance instead of creating new one

logger = logging.getLogger(__name__)

class QdrantManager:
    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        self.collection_name = "post_embeddings"
        self.redis_manager = redis_manager  # Use the existing instance

    async def init_collection(self):
        """Initialize collection if it doesn't exist"""
        try:
            # Convert synchronous operations to async pattern with proper error handling
            collections = self.client.get_collections()
            collection_exists = self.collection_name in [c.name for c in collections.collections]
            
            if not collection_exists:
                logger.info(f"Creating new collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=384,
                        distance=Distance.COSINE
                    )
                )
                self._create_indices()
                await self.optimize_storage()  # Configure optimizers after creation
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Error initializing Qdrant collection: {e}")
            # Don't raise exception to prevent transaction rollback

    def _create_indices(self):
        """Create payload indices"""
        try:
            indices = [
                ("post_id", "keyword"),
                ("author_id", "keyword"),
                ("created_at", "datetime"),
                ("hashtags", "keyword")
            ]
            
            for field_name, field_schema in indices:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_schema
                )
        except Exception as e:
            logger.error(f"Error creating indices: {e}")
            # Don't raise exception

    async def upsert_post_embedding(self, post_id: int, embedding: list, metadata: dict):
        """Store or update post embedding"""
        try:
            # Clean up metadata to ensure it's serializable
            clean_metadata = {
                "post_id": post_id,
                "author_id": metadata.get("author_id"),
                "created_at": metadata.get("created_at"),
                "hashtags": metadata.get("hashtags", [])
            }
            
            point = PointStruct(
                id=post_id,
                vector=embedding,
                payload=clean_metadata
            )
            
            # Use wait=True to ensure the operation completes
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
                wait=True
            )
            
            logger.info(f"Successfully upserted embedding for post {post_id}")
            return True
        except Exception as e:
            logger.error(f"Error upserting post embedding: {e}")
            # Log error but don't raise to prevent transaction rollback
            return False

    async def update_payload(self, post_id: int, metadata: Dict):
        """Update post metadata without changing embedding"""
        try:
            self.client.update_payload(
                collection_name=self.collection_name,
                payload=metadata,
                points=[post_id],
                wait=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating payload: {e}")
            # Log error but don't raise
            return False

    async def delete_post_embedding(self, post_id: int):
        """Delete post embedding when post is deleted"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[post_id]),
                wait=True
            )
            logger.info(f"Deleted embedding for post {post_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting post embedding: {e}")
            # Log error but don't raise
            return False

    async def optimize_storage(self):
        """Optimize storage and clean WAL"""
        try:
            self.client.update_collection(
                collection_name=self.collection_name,
                optimizer_config=models.OptimizersConfigDiff(
                    default_segment_number=2,
                    max_segment_size=100_000,
                    memmap_threshold=10_000,
                    vacuum_min_vector_number=1000,
                    flush_interval_sec=60
                )
            )
            logger.info("Storage optimization completed")
            return True
        except Exception as e:
            logger.error(f"Error optimizing storage: {e}")
            # Log error but don't raise
            return False

    async def search_similar_posts(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        offset: int = 0,
        filter_conditions: Optional[Dict] = None
    ) -> List[Dict]:
        """Search for similar posts using vector similarity with Redis caching"""
        try:
            cache_key = self._generate_search_cache_key(
                query_vector, 
                limit, 
                score_threshold,
                offset,
                filter_conditions
            )
            
            cached_results = await self.redis_manager.get_post(cache_key)
            if cached_results:
                logger.info(f"Cache hit for search query {cache_key}")
                return cached_results

            search_filter = self._prepare_search_filter(filter_conditions) if filter_conditions else None

            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                offset=offset,
                score_threshold=score_threshold,
                query_filter=search_filter
            )
            
            logger.debug(f"Raw search results: {search_results}")

            formatted_results = [{
                "post_id": result.id,
                "score": result.score,
                "metadata": result.payload,
            } for result in search_results]

            try:
                await self.redis_manager.set_post(cache_key, formatted_results)
            except Exception as cache_e:
                logger.error(f"Error caching search results: {cache_e}")
                # Continue even if caching fails
                
            return formatted_results

        except Exception as e:
            logger.error(f"Error in search_similar_posts: {e}")
            # Return empty results rather than raising exception
            return []

    def _prepare_search_filter(self, conditions: Dict) -> Dict:
        """Convert API filter conditions to Qdrant filter format"""
        qdrant_filter = {"must": []}
        
        if "author_id" in conditions:
            qdrant_filter["must"].append({
                "key": "author_id",
                "match": {"value": conditions["author_id"]}
            })
            
        if "created_after" in conditions:
            qdrant_filter["must"].append({
                "key": "created_at",
                "range": {"gte": str(conditions["created_after"])}
            })
            
        if "created_before" in conditions:
            qdrant_filter["must"].append({
                "key": "created_at",
                "range": {"lte": str(conditions["created_before"])}
            })
            
        if "hashtags" in conditions:
            qdrant_filter["must"].append({
                "key": "hashtags",
                "match": {"any": conditions["hashtags"]}
            })
            
        return qdrant_filter if qdrant_filter["must"] else None

    def _generate_search_cache_key(
        self,
        query_vector: List[float],
        limit: int,
        score_threshold: float,
        offset: int,
        filter_conditions: Optional[Dict]
    ) -> str:
        """Generate a deterministic cache key for search parameters"""
        vector_hash = hashlib.md5(str(query_vector).encode()).hexdigest()
        
        params = {
            "vector_hash": vector_hash,
            "limit": limit,
            "score_threshold": score_threshold,
            "offset": offset,
            "filters": filter_conditions
        }
        
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()
        
        return f"search_results:{params_hash}"

    async def clear_search_cache(self, pattern: Optional[str] = None):
        """Clear search results cache"""
        try:
            pattern = pattern or "search_results:*"
            await self.redis_manager.clear_pattern(pattern)
            logger.info("Cleared search cache with pattern: %s", str(pattern))
        except Exception as e:
            logger.error("Error clearing search cache: %s", str(e))