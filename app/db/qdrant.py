# app/db/qdrant.py
import hashlib
import json
import logging
from typing import Dict, List, Optional
from fastapi import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.core.config import settings
from app.db.redis import RedisManager

logger = logging.getLogger(__name__)


class QdrantManager:
    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        self.collection_name = "post_embeddings"
        self.redis_manager = RedisManager()

    async def init_collection(self):
        """Initialize the posts collection"""
        try:
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=384,  # Using MiniLM embedding size
                    distance=Distance.COSINE
                )
            )

            # Create payload index for filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="post_id",
                field_schema="keyword"
            )

            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="author_id",
                field_schema="keyword"
            )

            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="created_at",
                field_schema="datetime"
            )

        except Exception as e:
            print(f"Error initializing Qdrant collection: {e}")
            raise

    async def upsert_post_embedding(self, post_id: int, embedding: list, metadata: dict):
        """Store or update post embedding"""
        try:
            point = PointStruct(
                id=post_id,
                vector=embedding,
                payload={
                    "post_id": post_id,
                    "author_id": metadata.get("author_id"),
                    "created_at": metadata.get("created_at"),
                    "hashtags": metadata.get("hashtags", [])
                }
            )
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
        except Exception as e:
            print(f"Error upserting post embedding: {e}")
            raise

    async def search_similar_posts(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        offset: int = 0,
        filter_conditions: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar posts using vector similarity
        with Redis caching
        """
        try:
            # Generate cache key
            cache_key = self._generate_search_cache_key(
                query_vector, 
                limit, 
                score_threshold,
                offset,
                filter_conditions
            )
            
            # Try to get from cache
            cached_results = await self.redis_manager.get_post(cache_key)
            if cached_results:
                logger.info(f"Cache hit for search query {cache_key}")
                return cached_results

            # Convert filter conditions to Qdrant filter format if provided
            search_filter = None
            if filter_conditions:
                search_filter = self._prepare_search_filter(filter_conditions)

            # Perform search in Qdrant
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                offset=offset,
                score_threshold=score_threshold,
                query_filter=search_filter
            )

            # Process and format results
            formatted_results = []
            for result in search_results:
                formatted_result = {
                    "post_id": result.id,
                    "score": result.score,
                    "metadata": result.payload,
                }
                formatted_results.append(formatted_result)

            # Cache results with 5-minute TTL
            await self.redis_manager.set_post(cache_key, formatted_results, ttl=300)
            
            return formatted_results

        except Exception as e:
            logger.error(f"Error in search_similar_posts: {e}")
            raise

    def _generate_search_cache_key(
        self,
        query_vector: List[float],
        limit: int,
        score_threshold: float,
        offset: int,
        filter_conditions: Optional[Dict]
    ) -> str:
        """Generate a deterministic cache key for search parameters"""
        # Create a hash of the query vector (it could be large)
        vector_hash = hashlib.md5(str(query_vector).encode()).hexdigest()
        
        # Combine all search parameters
        params = {
            "vector_hash": vector_hash,
            "limit": limit,
            "score_threshold": score_threshold,
            "offset": offset,
            "filters": filter_conditions
        }
        
        # Create a deterministic string representation
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()
        
        return f"search_results:{params_hash}"

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

    async def clear_search_cache(self, pattern: Optional[str] = None):
        """Clear search results cache"""
        try:
            pattern = pattern or "search_results:*"
            await self.redis_manager.clear_pattern(pattern)
            logger.info("Cleared search cache with pattern: %s", str(pattern))
        except Exception as e:
            logger.error("Error clearing search cache: %s", str(e))