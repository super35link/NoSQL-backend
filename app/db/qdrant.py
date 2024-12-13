# app/db/qdrant.py
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.core.config import settings

class QdrantManager:
    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        self.collection_name = "post_embeddings"

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
        query_vector: list,
        limit: int = 10,
        score_threshold: float = 0.7
    ):
        """Search for similar posts"""
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold
            )
            return results
        except Exception as e:
            print(f"Error searching similar posts: {e}")
            raise