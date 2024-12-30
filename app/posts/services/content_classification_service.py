import asyncio
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Set, Optional
from sqlalchemy.sql.selectable import Select
from datetime import datetime, timedelta
import logging
from fastapi import HTTPException
from transformers import pipeline
from app.db.models import User, Hashtag, post_hashtags
from app.db.mongodb import get_mongodb
from app.db.qdrant import QdrantManager
from app.db.redis import RedisManager
from app.posts.schemas.classification_schemas import ContentClassification, TopicResponse
from .embedding_service import PostEmbeddingService

logger = logging.getLogger(__name__)

class ContentClassificationService:
    def __init__(self):
        self.mongodb = get_mongodb()
        self.qdrant = QdrantManager()
        self.embedding_service = PostEmbeddingService()
        self.redis_manager = RedisManager()
        
        # Initialize classification models
        self.sentiment_analyzer = pipeline("sentiment-analysis")
        self.topic_classifier = pipeline("text-classification", model="facebook/bart-large-mnli")
        self.language_detector = pipeline("text-classification", model="papluca/xlm-roberta-base-language-detection")
        self.entity_recognizer = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english")
        
        # Collections
        self.trending_collection = self.mongodb.get_collection("trending_metrics")
        self.topic_collection = self.mongodb.get_collection("topic_classifications")
        self.moderation_collection = self.mongodb.get_collection("moderation_results")


    async def process_content(
        self, 
        session: AsyncSession, 
        post_id: int, 
        content: str,
        mentioned_user_ids: Set[int],
        hashtags: Set[str]
    ) -> ContentClassification:
        """Process new content with enhanced classification"""
        try:
            # Check cache first
            cache_key = f"content_classification:{post_id}"
            cached_result = await self.redis_manager.get_post(cache_key)
            if cached_result:
                return ContentClassification(**cached_result)

            # Run classifications in parallel
            classifications = await self._parallel_classify(content)
            
            # Get usernames for response
            select_stmt: Select = select(User.username).where(User.id.in_(mentioned_user_ids))
            result = await session.execute(select_stmt)
            mentioned_users = result.scalars()
            mentioned_usernames: List[str] = [username for username in mentioned_users]

            # Generate embedding and classify topics
            embedding = await self.embedding_service.generate_embedding(content)
            raw_topics = await self._classify_topics(content, embedding)
            
            # Convert raw topics to TopicResponse objects
            topics = [
                TopicResponse(
                    topic=t["topic"],
                    confidence=t["confidence"],
                    related_hashtags=t.get("related_hashtags", [])
                ) for t in raw_topics
            ]
            
            # Store topic classifications
            await self.topic_collection.insert_one({
                "post_id": post_id,
                "topics": [t.dict() for t in topics],
                "embedding": embedding,
                "timestamp": datetime.utcnow()
            })

            # Check content moderation
            moderation_result = await self._moderate_content(content)
            if not moderation_result["is_safe"]:
                raise HTTPException(
                    status_code=400,
                    detail="Content violates community guidelines"
                )
            
            # Store moderation result
            await self.moderation_collection.insert_one({
                "post_id": post_id,
                "result": moderation_result,
                "timestamp": datetime.utcnow()
            })
            
            # Create ContentClassification response
            classification = ContentClassification(
                hashtags=list(hashtags),
                topics=topics,
                content_type="post",
                sentiment=classifications["sentiment"],       # Add these from
                language=classifications["language"],         # parallel_classify
                entity_analysis=classifications["entities"],   # results
                mentions=mentioned_usernames
            )
            
            # Cache the result
            await self.redis_manager.set_post(cache_key, classification.dict())
            
            # Update trending metrics asynchronously
            asyncio.create_task(self._async_update_trending_metrics(hashtags, topics))
            
            return classification

        except Exception as e:
            logger.error(f"Error processing content classification: {e}")
            raise
        
    async def _async_update_trending_metrics(
        self,
        hashtags: Set[str],
        topics: List[Dict[str, float]]
    ) -> None:
        """Update trending metrics asynchronously"""
        try:
            timestamp = datetime.utcnow()
            
            # Prepare bulk operations for hashtags
            hashtag_ops = [
                {
                    "type": "hashtag",
                    "tag": tag,
                    "timestamp": timestamp,
                    "engagement_value": 1
                }
                for tag in hashtags
            ]
            
            # Prepare bulk operations for topics
            topic_ops = [
                {
                    "type": "topic",
                    "topic": topic["topic"],
                    "confidence": topic["confidence"],
                    "timestamp": timestamp
                }
                for topic in topics
            ]
            
            # Execute in parallel
            await asyncio.gather(
                self.trending_collection.insert_many(hashtag_ops),
                self.trending_collection.insert_many(topic_ops)
            )
            
        except Exception as e:
            logger.error(f"Error updating trending metrics: {e}")
            logger.error(f"Hashtag operations: {hashtag_ops}")
            logger.error(f"Topic operations: {topic_ops}")
            # Continue execution even if trending updates fail

    async def get_trending_hashtags(
        self,
        timeframe: str = "24h",
        limit: int = 10,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get trending hashtags with enhanced analytics"""
        try:
            # Check cache
            cache_key = f"trending_hashtags:{timeframe}:{category}:{limit}"
            cached_result = await self.redis_manager.get_post(cache_key)
            if cached_result:
                return cached_result

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
                }
            ]
            
            if category:
                pipeline.append({
                    "$match": {"category": category}
                })
                
            pipeline.extend([
                {
                    "$group": {
                        "_id": "$tag",
                        "count": {"$sum": 1},
                        "last_used": {"$max": "$timestamp"},
                        "unique_users": {"$addToSet": "$user_id"},
                        "engagement_score": {"$sum": "$engagement_value"}
                    }
                },
                {
                    "$project": {
                        "tag": "$_id",
                        "count": 1,
                        "last_used": 1,
                        "unique_users": {"$size": "$unique_users"},
                        "velocity": {
                            "$divide": [
                                "$count",
                                {"$subtract": [
                                    "$$NOW",
                                    "$first_used"
                                ]}
                            ]
                        },
                        "engagement_rate": {
                            "$divide": ["$engagement_score", "$count"]
                        }
                    }
                },
                {
                    "$addFields": {
                        "trend_score": {
                            "$multiply": [
                                "$count",
                                "$velocity",
                                {"$add": [1, "$engagement_rate"]}
                            ]
                        }
                    }
                },
                {"$sort": {"trend_score": -1}},
                {"$limit": limit}
            ])
            
            results = await self.trending_collection.aggregate(pipeline).to_list(None)
            
            # Cache results
            await self.redis_manager.set_post(cache_key, results, ttl=300)  # 5 minutes cache
            
            return results

        except Exception as e:
            logger.error(f"Error fetching trending hashtags: {e}")
            raise

    async def _parallel_classify(self, content: str) -> Dict:
        """Perform parallel content classification"""
        tasks = [
            self._analyze_sentiment(content),
            self._detect_language(content),
            self._extract_entities(content)
        ]
        results = await asyncio.gather(*tasks)
        
        return {
            "sentiment": results[0],
            "language": results[1],
            "entities": results[2]
        }

    async def _analyze_sentiment(self, content: str) -> Dict:
        """Analyze content sentiment"""
        result = self.sentiment_analyzer(content)[0]
        return {
            "label": result["label"],
            "score": result["score"]
        }

    async def _moderate_content(self, content: str) -> Dict:
        """Check content against moderation rules with caching"""
        try:
            # Generate cache key based on content hash
            content_hash = hashlib.md5(content.encode()).hexdigest()
            cache_key = f"content_moderation:{content_hash}"
            
            # Check cache
            cached_result = await self.redis_manager.get_post(cache_key)
            if cached_result:
                return cached_result

            # If not in cache, perform moderation...
            result = {
                "is_safe": True,
                "rating": "G",
                "flags": []
            }
            
            # Cache moderation result for 24 hours
            await self.redis_manager.set_post(cache_key, result, ttl=86400)
            
            return result

        except Exception as e:
            logger.error(f"Error in content moderation: {e}")
            # Default to safe if moderation fails
            return {"is_safe": True, "rating": "G", "flags": []}

    async def _batch_store_hashtags(
        self,
        session: AsyncSession,
        post_id: int,
        hashtags: Set[str]
    ):
        """Store hashtags with batching"""
        if not hashtags:
            return

        # Get or create hashtags in batch
        existing_hashtags = await session.execute(
            select(Hashtag).where(Hashtag.tag.in_(hashtags))
        )
        existing_hashtags = {h.tag: h for h in existing_hashtags.scalars()}
        
        # Create new hashtags
        new_hashtags = []
        for tag in hashtags:
            if tag not in existing_hashtags:
                new_hashtag = Hashtag(tag=tag)
                session.add(new_hashtag)
                new_hashtags.append(new_hashtag)
        
        if new_hashtags:
            await session.flush()
            
        # Create associations
        for tag in hashtags:
            hashtag = existing_hashtags.get(tag) or new_hashtags.pop(0)
            await session.execute(
                post_hashtags.insert().values(
                    post_id=post_id,
                    hashtag_id=hashtag.id
                )
            )

    async def _detect_language(self, content: str) -> Dict[str, str]:
        """Detect content language"""
        try:
            # Currently initializing in the function because we haven't set it in __init__
            language_detector = pipeline("text-classification", model="papluca/xlm-roberta-base-language-detection")
            
            result = language_detector(content)[0]
            return {
                "language": result["label"],
                "confidence": result["score"]
            }
        except Exception as e:
            logger.error(f"Error detecting language: {e}")
            return {"language": "unknown", "confidence": 0.0}

    async def _extract_entities(self, content: str) -> List[Dict]:
        """Extract named entities from content"""
        try:
            # Currently initializing in the function because we haven't set it in __init__
            entity_recognizer = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english")
            
            entities = entity_recognizer(content)
            
            # Group and deduplicate entities
            processed_entities = []
            seen = set()
            
            for entity in entities:
                key = (entity["entity"], entity["word"])
                if key not in seen:
                    processed_entities.append({
                        "text": entity["word"],
                        "type": entity["entity"],
                        "confidence": entity["score"]
                    })
                    seen.add(key)
            
            return processed_entities
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return []    
    async def _classify_topics(
        self,
        content: str,
        embedding: list
    ) -> List[Dict[str, float]]:
        """Classify content into topics with confidence scores"""
        try:
            # Use the initialized topic classifier
            results = self.topic_classifier(
                content,
                candidate_labels=["technology", "politics", "entertainment", "sports", "business"]
            )
            
            # Format results
            topics = [
                {
                    "topic": label,
                    "confidence": score
                }
                for label, score in zip(results["labels"], results["scores"])
            ]
            
            # Store in MongoDB for analytics
            await self.topic_collection.insert_one({
                "content_embedding": embedding,
                "topics": topics,
                "timestamp": datetime.utcnow()
            })
            
            return topics

        except Exception as e:
            logger.error(f"Error classifying topics: {e}")
            return []  # Return empty list on error