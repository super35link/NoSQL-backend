from sentence_transformers import SentenceTransformer
from app.db.qdrant import QdrantManager
from typing import List, Dict, Union
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PostEmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.qdrant = QdrantManager()

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for single text content"""
        try:
            cleaned_text = self._preprocess_text(text)
            embedding = self.model.encode(cleaned_text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts at once"""
        try:
            cleaned_texts = [self._preprocess_text(text) for text in texts]
            embeddings = self.model.encode(cleaned_texts)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise

    async def process_post(self, post_id: int, content: str, metadata: Dict) -> List[float]:
        """Process a single post and store its embedding"""
        try:
            embedding = await self.generate_embedding(content)
            
            post_metadata = {
                "author_id": metadata.get("author_id"),
                "created_at": metadata.get("created_at", datetime.utcnow()),
                "hashtags": self._extract_hashtags(content)
            }

            await self.qdrant.upsert_post_embedding(
                post_id=post_id,
                embedding=embedding,
                metadata=post_metadata
            )
            
            return embedding

        except Exception as e:
            logger.error(f"Error processing post: {e}")
            raise

    async def process_posts_batch(
        self,
        posts: List[Dict[str, Union[int, str, Dict]]]
    ) -> List[List[float]]:
        """Process multiple posts in batch"""
        try:
            # Extract contents and generate embeddings in batch
            contents = [post["content"] for post in posts]
            embeddings = await self.generate_embeddings_batch(contents)
            
            # Process each post with its embedding
            for post_data, embedding in zip(posts, embeddings):
                post_metadata = {
                    "author_id": post_data["metadata"].get("author_id"),
                    "created_at": post_data["metadata"].get("created_at", datetime.utcnow()),
                    "hashtags": self._extract_hashtags(post_data["content"])
                }
                
                await self.qdrant.upsert_post_embedding(
                    post_id=post_data["post_id"],
                    embedding=embedding,
                    metadata=post_metadata
                )
            
            return embeddings

        except Exception as e:
            logger.error(f"Error processing posts batch: {e}")
            raise

    def _preprocess_text(self, text: str) -> str:
        """Clean and preprocess text"""
        text = ' '.join(text.split())
        max_length = 512
        words = text.split()
        if len(words) > max_length:
            text = ' '.join(words[:max_length])
        return text

    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from text"""
        return [word[1:] for word in text.split() if word.startswith('#')]

    async def update_post_metadata(self, post_id: int, metadata: Dict):
        """Update post metadata in Qdrant without changing embedding"""
        try:
            await self.qdrant.update_payload(post_id, metadata)
        except Exception as e:
            logger.error(f"Error updating post metadata: {e}")
            raise