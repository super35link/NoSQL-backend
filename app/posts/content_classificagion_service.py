from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Dict, Set, Optional
from datetime import datetime, timedelta
import re
from collections import Counter
import logging

from app.db.models import Post, Hashtag, User, post_hashtags, post_mentions
from app.db.mongodb import get_mongodb
from app.db.qdrant import QdrantManager
from .embedding_service import PostEmbeddingService

logger = logging.getLogger(__name__)

class ContentClassificationService:
    def __init__(self):
        self.mongodb = get_mongodb()
        self.qdrant = QdrantManager()
        self.embedding_service = PostEmbeddingService()
        
        # Collections
        self.trending_collection = self.mongodb.trending_metrics
        self.topic_collection = self.mongodb.topic_classifications

    async def process_content(
        self, 
        session: AsyncSession, 
        post_id: int, 
        content: str,
        author_id: int
    ) -> Dict:
        """Process new content for classification"""
        try:
            # Extract classifications
            hashtags = self._extract_hashtags(content)
            mentions = self._extract_mentions(content)
            
            # Store in PostgreSQL
            await self._store_hashtags(session, post_id, hashtags)
            await self._store_mentions(session, post_id, mentions)
            
            # Generate embedding and classify topics
            embedding = await self.embedding_service.generate_embedding(content)
            topics = await self._classify_topics(content, embedding)
            
            # Update trending metrics
            await self._update_trending_metrics(hashtags, topics)
            
            return {
                "hashtags": list(hashtags),
                "mentions": list(mentions),
                "topics": topics
            }
        except Exception as e:
            logger.error(f"Error processing content classification: {e}")
            raise

    async def get_trending_hashtags(
        self,
        timeframe: str = "24h",
        limit: int = 10
    ) -> List[Dict]:
        """Get trending hashtags with their metrics"""
        time_ranges = {
            "1h": 1,
            "24h": 24,
            "7d": 168,
            "30d": 720
        }
        hours = time_ranges.get(timeframe, 24)
        
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": datetime.utcnow() - timedelta(hours=hours)
                    },
                    "type": "hashtag"
                }
            },
            {
                "$group": {
                    "_id": "$tag",
                    "count": {"$sum": 1},
                    "last_used": {"$max": "$timestamp"},
                    "unique_users": {"$addToSet": "$user_id"}
                }
            },
            {
                "$project": {
                    "tag": "$_id",
                    "count": 1,
                    "last_used": 1,
                    "unique_users": {"$size": "$unique_users"},
                    "score": {
                        "$multiply": [
                            "$count",
                            {"$size": "$unique_users"}
                        ]
                    }
                }
            },
            {"$sort": {"score": -1}},
            {"$limit": limit}
        ]
        
        results = await self.trending_collection.aggregate(pipeline).to_list(None)
        return results

    async def get_similar_content(
        self,
        session: AsyncSession,
        post_id: int,
        limit: int = 5
    ) -> List[Dict]:
        """Get similar content based on topics and hashtags"""
        # Get post details
        post = await session.get(Post, post_id)
        if not post:
            raise ValueError("Post not found")
            
        # Get post's hashtags
        hashtags = await self._get_post_hashtags(session, post_id)
        
        # Get post's embedding from Qdrant
        post_data = await self.qdrant.get_post(post_id)
        if not post_data:
            raise ValueError("Post embedding not found")
            
        # Search for similar content
        similar_posts = await self.qdrant.search(
            query_vector=post_data["embedding"],
            query_filter={
                "should": [
                    {"has_id": str(tag_id)} for tag_id in hashtags
                ]
            } if hashtags else None,
            limit=limit
        )
        
        return similar_posts

    async def get_topic_distribution(
        self,
        session: AsyncSession,
        username: Optional[str] = None,
        hashtag: Optional[str] = None
    ) -> Dict:
        """Get topic distribution for user or hashtag"""
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": datetime.utcnow() - timedelta(days=30)
                    }
                }
            }
        ]
        
        if username:
            user = await self._get_user_by_username(session, username)
            if not user:
                raise ValueError(f"User {username} not found")
            pipeline[0]["$match"]["user_id"] = user.id
            
        if hashtag:
            pipeline[0]["$match"]["hashtags"] = hashtag
            
        pipeline.extend([
            {
                "$group": {
                    "_id": "$topic",
                    "count": {"$sum": 1},
                    "confidence_sum": {"$sum": "$confidence"}
                }
            },
            {
                "$project": {
                    "topic": "$_id",
                    "count": 1,
                    "average_confidence": {
                        "$divide": ["$confidence_sum", "$count"]
                    }
                }
            },
            {"$sort": {"count": -1}}
        ])
        
        results = await self.topic_collection.aggregate(pipeline).to_list(None)
        return {
            "username": username,
            "hashtag": hashtag,
            "topics": results
        }

    async def suggest_hashtags(
        self,
        content: str,
        limit: int = 5
    ) -> List[str]:
        """Suggest hashtags based on content"""
        try:
            # Generate embedding
            embedding = await self.embedding_service.generate_embedding(content)
            
            # Find similar content
            similar_posts = await self.qdrant.search(
                query_vector=embedding,
                limit=10  # Get more to aggregate hashtags
            )
            
            # Collect hashtags from similar posts
            hashtags = []
            for post in similar_posts:
                hashtags.extend(post.get("payload", {}).get("hashtags", []))
            
            # Count and sort hashtags
            if hashtags:
                counter = Counter(hashtags)
                suggested = [tag for tag, _ in counter.most_common(limit)]
                return suggested
            
            return []
            
        except Exception as e:
            logger.error(f"Error suggesting hashtags: {e}")
            return []

    # Helper methods
    def _extract_hashtags(self, content: str) -> Set[str]:
        """Extract hashtags from content"""
        pattern = r'#(\w+)'
        return set(re.findall(pattern, content))

    def _extract_mentions(self, content: str) -> Set[str]:
        """Extract mentions from content"""
        pattern = r'@(\w+)'
        return set(re.findall(pattern, content))

    async def _store_hashtags(
        self,
        session: AsyncSession,
        post_id: int,
        hashtags: Set[str]
    ):
        """Store hashtags in PostgreSQL"""
        for tag in hashtags:
            # Get or create hashtag
            result = await session.execute(
                select(Hashtag).where(Hashtag.tag == tag)
            )
            hashtag = result.scalar_one_or_none()
            
            if not hashtag:
                hashtag = Hashtag(tag=tag)
                session.add(hashtag)
                await session.flush()
            
            # Create association
            await session.execute(
                post_hashtags.insert().values(
                    post_id=post_id,
                    hashtag_id=hashtag.id
                )
            )

    async def _store_mentions(
        self,
        session: AsyncSession,
        post_id: int,
        mentions: Set[str]
    ):
        """Store mentions in PostgreSQL"""
        for username in mentions:
            user = await self._get_user_by_username(session, username)
            if user:
                await session.execute(
                    post_mentions.insert().values(
                        post_id=post_id,
                        user_id=user.id
                    )
                )

    async def _classify_topics(
        self,
        content: str,
        embedding: List[float]
    ) -> List[Dict]:
        """Classify content into topics"""
        # This would integrate with a topic classification model
        # For now, return placeholder topics based on embedding similarity
        similar_docs = await self.qdrant.search(
            query_vector=embedding,
            limit=5
        )
        
        # Aggregate topics from similar documents
        topics = []
        for doc in similar_docs:
            if doc.get("payload", {}).get("topics"):
                topics.extend(doc["payload"]["topics"])
        
        return list(set(topics))

    async def _update_trending_metrics(
        self,
        hashtags: Set[str],
        topics: List[str]
    ):
        """Update trending metrics in MongoDB"""
        timestamp = datetime.utcnow()
        
        # Update hashtag metrics
        for tag in hashtags:
            await self.trending_collection.insert_one({
                "type": "hashtag",
                "tag": tag,
                "timestamp": timestamp
            })
            
        # Update topic metrics
        for topic in topics:
            await self.trending_collection.insert_one({
                "type": "topic",
                "topic": topic,
                "timestamp": timestamp
            })

    async def _get_user_by_username(
        self,
        session: AsyncSession,
        username: str
    ) -> Optional[User]:
        """Get user by username"""
        result = await session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def _get_post_hashtags(
        self,
        session: AsyncSession,
        post_id: int
    ) -> List[int]:
        """Get hashtag IDs for a post"""
        result = await session.execute(
            select(Hashtag.id)
            .join(post_hashtags)
            .where(post_hashtags.c.post_id == post_id)
        )
        return [r[0] for r in result]