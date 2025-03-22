from sentence_transformers import SentenceTransformer
from app.db.qdrant import QdrantManager
from typing import List, Dict, Union, Optional
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class PostEmbeddingService:
    def __init__(self):
        self._model = None
        self.qdrant = QdrantManager()

    @property
    def model(self):
        if self._model is None:
            logger.info("Initializing sentence transformer model")
            self._model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        return self._model

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for single text content"""
        try:
            cleaned_text = self._preprocess_text(text)
            embedding = self.model.encode(cleaned_text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            # Return None instead of raising
            return None

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts at once"""
        try:
            cleaned_texts = [self._preprocess_text(text) for text in texts]
            embeddings = self.model.encode(cleaned_texts)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            # Return empty list instead of raising
            return []

    async def process_post(self, post_id: int, content: str, metadata: Dict) -> Optional[List[float]]:
        """Process a single post and store its embedding with error handling"""
        try:
            # Generate embedding
            embedding = await self.generate_embedding(content)
            if embedding is None:
                logger.error(f"Failed to generate embedding for post {post_id}")
                return None
            
            # Clean metadata for storage
            clean_metadata = {}
            
            # Handle author_id
            clean_metadata["author_id"] = metadata.get("author_id")
            
            # Handle created_at - ensure it's a string
            if "created_at" in metadata:
                if isinstance(metadata["created_at"], datetime):
                    clean_metadata["created_at"] = metadata["created_at"].isoformat()
                else:
                    clean_metadata["created_at"] = metadata["created_at"]
            else:
                clean_metadata["created_at"] = datetime.utcnow().isoformat()
            
            # Handle hashtags
            if "hashtags" in metadata and metadata["hashtags"]:
                clean_metadata["hashtags"] = metadata["hashtags"]
            else:
                clean_metadata["hashtags"] = self._extract_hashtags(content)

            # Store in Qdrant but don't propagate exceptions
            try:
                await self.qdrant.upsert_post_embedding(
                    post_id=post_id,
                    embedding=embedding,
                    metadata=clean_metadata
                )
            except Exception as qdrant_err:
                logger.error(f"Error storing embedding in Qdrant: {qdrant_err}")
                # Continue even if Qdrant storage fails
            
            return embedding

        except Exception as e:
            logger.error(f"Error processing post {post_id}: {e}")
            # Return None instead of raising
            return None

    async def process_posts_batch(
        self,
        posts: List[Dict[str, Union[int, str, Dict]]]
    ) -> List[List[float]]:
        """Process multiple posts in batch with error handling"""
        try:
            # Extract contents and generate embeddings in batch
            contents = [post.get("content", "") for post in posts]
            embeddings = await self.generate_embeddings_batch(contents)
            
            if not embeddings:
                logger.error("Failed to generate batch embeddings")
                return []
            
            # Process each post with its embedding
            for i, (post_data, embedding) in enumerate(zip(posts, embeddings)):
                try:
                    post_id = post_data.get("post_id")
                    if post_id is None:
                        logger.error(f"Missing post_id in batch item {i}")
                        continue
                        
                    metadata = post_data.get("metadata", {})
                    
                    # Clean metadata
                    clean_metadata = {
                        "author_id": metadata.get("author_id"),
                        "created_at": metadata.get("created_at", datetime.utcnow().isoformat()),
                        "hashtags": metadata.get("hashtags") or self._extract_hashtags(post_data.get("content", ""))
                    }
                    
                    # Store in Qdrant but handle failures for individual items
                    try:
                        await self.qdrant.upsert_post_embedding(
                            post_id=post_id,
                            embedding=embedding,
                            metadata=clean_metadata
                        )
                    except Exception as e:
                        logger.error(f"Error storing embedding for post {post_id} in batch: {e}")
                        # Continue with next item
                except Exception as item_err:
                    logger.error(f"Error processing batch item {i}: {item_err}")
                    # Continue with next item
            
            return embeddings

        except Exception as e:
            logger.error(f"Error processing posts batch: {e}")
            # Return empty list instead of raising
            return []

    def _preprocess_text(self, text: str) -> str:
        """Clean and preprocess text"""
        if not text:
            return ""  # Handle empty text
            
        text = ' '.join(text.split())
        max_length = 512
        words = text.split()
        if len(words) > max_length:
            text = ' '.join(words[:max_length])
        return text

    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from text"""
        if not text:
            return []
            
        return [word[1:] for word in text.split() if word.startswith('#')]

    async def update_post_metadata(self, post_id: int, metadata: Dict) -> bool:
        """Update post metadata in Qdrant without changing embedding"""
        try:
            return await self.qdrant.update_payload(post_id, metadata)
        except Exception as e:
            logger.error(f"Error updating post metadata: {e}")
            return False