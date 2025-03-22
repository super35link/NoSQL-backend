# app/posts/services/content_classification_service.py
import asyncio
import hashlib
from httpx import post
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import List, Dict, Set, Optional, Any
from sqlalchemy.sql.selectable import Select
from datetime import datetime, timedelta
import logging
from fastapi import HTTPException
from app.db.models import Post, User, Hashtag, post_hashtags
from app.db.mongodb import get_mongodb
from app.db.qdrant import QdrantManager
from app.db.redis import RedisManager
from app.posts.schemas.classification_schemas import ContentClassification, TopicResponse
from .embedding_service import PostEmbeddingService
from app.ml.model_manager import get_model_manager

logger = logging.getLogger(__name__)

class ContentClassificationService:
    """
    Service for content classification, topic extraction, and trend analysis.
    Uses a lazy-loading pattern for ML models to optimize resource usage.
    """
    def __init__(self):
        self.mongodb = get_mongodb()
        self.qdrant = QdrantManager()
        self.embedding_service = PostEmbeddingService()
        self.redis_manager = RedisManager()
        self.model_manager = get_model_manager()
        
        # Collections
        self.trending_collection = self.mongodb.get_collection("trending_metrics")
        self.topic_collection = self.mongodb.get_collection("topic_classifications")
        self.moderation_collection = self.mongodb.get_collection("moderation_results")
        
        # Default classification settings
        self.candidate_topics = ["technology", "politics", "entertainment", "sports", "business"]
        self.default_cache_ttl = 3600  # 1 hour
        self.moderation_cache_ttl = 86400  # 24 hours
        self.trending_cache_ttl = 300  # 5 minutes

    async def process_content(
        self, 
        session: AsyncSession, 
        post_id: int, 
        content: str,
        mentioned_user_ids: Set[int],
        hashtags: Set[str]
    ) -> ContentClassification:
        """
        Process new content with enhanced classification.
        
        Args:
            session: Database session
            post_id: ID of the post being processed
            content: Text content to analyze
            mentioned_user_ids: Set of user IDs mentioned in the content
            hashtags: Set of hashtags in the content
            
        Returns:
            ContentClassification object with analysis results
            
        Raises:
            HTTPException: If content violates moderation rules
            Exception: For processing errors
        """
        try:
            # Input validation
            if not content or len(content.strip()) == 0:
                raise ValueError("Content cannot be empty")
                
            # Check cache first
            cache_key = f"content_classification:{post_id}"
            cached_result = await self.redis_manager.get_post(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for post {post_id}")
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
            
            # Store topic classifications - wrap in try/except to prevent main flow failure
            try:
                await self.topic_collection.insert_one({
                    "post_id": post_id,
                    "topics": [t.dict() for t in topics],
                    "embedding": embedding,
                    "timestamp": datetime.utcnow()
                })
            except Exception as e:
                logger.error(f"Error storing topic classification: {e}")
                # Continue processing despite this error
            
            # Check content moderation
            moderation_result = await self._moderate_content(content)
            if not moderation_result["is_safe"]:
                logger.warning(f"Content moderation failed for post {post_id}: {moderation_result['flags']}")
                raise HTTPException(
                    status_code=400,
                    detail="Content violates community guidelines"
                )
            
            # Store moderation result - wrap in try/except to prevent main flow failure
            try:
                await self.moderation_collection.insert_one({
                    "post_id": post_id,
                    "result": moderation_result,
                    "timestamp": datetime.utcnow()
                })
            except Exception as e:
                logger.error(f"Error storing moderation result: {e}")
                # Continue processing despite this error
            
            # Create ContentClassification response
            classification = ContentClassification(
                hashtags=list(hashtags),
                topics=topics,
                content_type="post",
                sentiment=classifications["sentiment"],
                language=classifications["language"],
                entity_analysis=classifications["entities"],
                mentions=mentioned_usernames
            )
            
            # Cache the result
            await self.redis_manager.set_post(cache_key, classification.dict(), ttl=self.default_cache_ttl)
            
            # Update trending metrics asynchronously - don't await this
            asyncio.create_task(self._async_update_trending_metrics(
            hashtags=hashtags, 
            topics=topics,
            user_id=post.author_id  # Pass the author ID
))
            
            # Store hashtags with batching - this is important for database consistency
            await self._batch_store_hashtags(session, post_id, hashtags)
            
            return classification

        except HTTPException:
            # Re-raise HTTP exceptions without modification
            raise
        except Exception as e:
            logger.error(f"Error processing content classification for post {post_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error processing content: {str(e)}"
            )
        
    async def _async_update_trending_metrics(
        self,
        hashtags: Set[str],
        topics: List[Dict[str, float]],
        user_id: Optional[int] = None
    ) -> None:
        """
        Update trending metrics asynchronously.
        This method is meant to be called as a background task.
        
        Args:
            hashtags: Set of hashtags
            topics: List of topic dictionaries with confidence scores
            user_id: Optional user ID who created the content
        """
        try:
            timestamp = datetime.utcnow()
            
            # Skip processing if there's nothing to update
            if not hashtags and not topics:
                return
                
            # Prepare bulk operations for hashtags
            hashtag_ops = [
                {
                    "type": "hashtag",
                    "tag": tag,
                    "timestamp": timestamp,
                    "first_used": timestamp,  # Ensure this field exists
                    "user_id": user_id,  # Include user ID if available
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
                    "timestamp": timestamp,
                    "first_used": timestamp,  # Ensure this field exists
                    "user_id": user_id,  # Include user ID if available
                    "engagement_value": topic["confidence"]  # Use confidence as engagement
                }
                for topic in topics if topic["confidence"] > 0.3  # Only include topics with reasonable confidence
            ]
            
            # Log what we're inserting
            logger.info(f"Updating {len(hashtag_ops)} hashtags and {len(topic_ops)} topics")
            if hashtag_ops:
                logger.debug(f"Hashtags: {[op['tag'] for op in hashtag_ops]}")
            
            # Execute in parallel with proper error handling for each operation
            tasks = []
            
            if hashtag_ops:
                tasks.append(self._safe_insert_many(self.trending_collection, hashtag_ops, "hashtag"))
                
            if topic_ops:
                tasks.append(self._safe_insert_many(self.trending_collection, topic_ops, "topic"))
                
            if tasks:
                await asyncio.gather(*tasks)
                
        except Exception as e:
            logger.error(f"Error updating trending metrics: {e}")
            logger.error(f"Hashtag operations: {hashtag_ops if 'hashtag_ops' in locals() else 'not created'}")
            logger.error(f"Topic operations: {topic_ops if 'topic_ops' in locals() else 'not created'}")
            
    async def _safe_insert_many(self, collection: Any, documents: List[Dict], operation_type: str) -> None:
        """Helper method to safely insert many documents with retries"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                await collection.insert_many(documents)
                return
            except Exception as e:
                retry_count += 1
                logger.warning(f"Error in {operation_type} insertion (attempt {retry_count}): {e}")
                if retry_count >= max_retries:
                    logger.error(f"Failed to insert {operation_type} documents after {max_retries} attempts")
                    return
                await asyncio.sleep(0.5 * retry_count)  # Exponential backoff

    async def get_trending_hashtags(
        self,
        timeframe: str = "24h",
        limit: int = 10,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        Get trending hashtags with focus on velocity and trend score.
        
        Args:
            timeframe: Time period for trend analysis ("1h", "24h", "7d", "30d")
            limit: Maximum number of results to return
            category: Optional category filter (ignored if not used)
            
        Returns:
            List of trending hashtag objects sorted by velocity
        """
        try:
            # Input validation
            valid_timeframes = {"1h", "24h", "7d", "30d"}
            if timeframe not in valid_timeframes:
                timeframe = "24h"
                
            if limit < 1 or limit > 100:
                limit = 10
            
            # Check cache
            cache_key = f"trending_hashtags:{timeframe}:{limit}"
            cached_result = await self.redis_manager.get_post(cache_key)
            if cached_result:
                return cached_result

            # Time range mapping
            time_ranges = {
                "1h": 1,
                "24h": 24,
                "7d": 168,
                "30d": 720
            }
            hours = time_ranges.get(timeframe, 24)
            time_threshold = datetime.utcnow() - timedelta(hours=hours)
            
            # Build simplified MongoDB aggregation pipeline
            pipeline = [
                # Match documents in the timeframe
                {
                    "$match": {
                        "timestamp": {"$gte": time_threshold},
                        "type": "hashtag"
                    }
                },
                # Group by tag and calculate metrics
                {
                    "$group": {
                        "_id": "$tag",
                        "tag": {"$first": "$tag"},
                        "count": {"$sum": 1},
                        "latest": {"$max": "$timestamp"},
                        "earliest": {"$min": "$timestamp"},
                        "engagement_value": {"$sum": "$engagement_value"}
                    }
                },
                # Calculate time-based metrics
                {
                    "$addFields": {
                        "timespan_hours": {
                            "$divide": [
                                {"$subtract": ["$latest", "$earliest"]},
                                3600000  # Convert ms to hours
                            ]
                        }
                    }
                },
                # Calculate velocity (posts per hour)
                {
                    "$addFields": {
                        "velocity": {
                            "$cond": [
                                {"$eq": ["$timespan_hours", 0]},
                                "$count",  # If timespan is 0, velocity equals count
                                {"$divide": ["$count", {"$max": ["$timespan_hours", 1]}]}
                            ]
                        },
                        "engagement_rate": {
                            "$divide": [
                                {"$max": ["$engagement_value", 1]},
                                {"$max": ["$count", 1]}
                            ]
                        }
                    }
                },
                # Calculate trend score
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
                # Sort by trend score
                {"$sort": {"trend_score": -1}},
                # Limit results
                {"$limit": limit},
                # Project only needed fields
                {
                    "$project": {
                        "_id": 0,
                        "tag": 1,
                        "count": 1,
                        "velocity": 1,
                        "engagement_rate": 1,
                        "trend_score": 1
                    }
                }
            ]
            
            # Execute pipeline
            try:
                raw_results = await asyncio.wait_for(
                    self.trending_collection.aggregate(pipeline).to_list(None),
                    timeout=5.0
                )
                
                # Format results for frontend (simplified)
                formatted_results = self._format_trending_response(raw_results)
                
                # Log results
                logger.info(f"Found {len(formatted_results)} trending hashtags")
                
                # Cache results
                await self.redis_manager.set_post(cache_key, formatted_results, ttl=self.trending_cache_ttl)
                
                return formatted_results
                
            except asyncio.TimeoutError:
                logger.error("Timeout executing trending hashtags pipeline")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching trending hashtags: {e}")
            return []
                
        except Exception as e:
            logger.error(f"Error fetching trending hashtags: {e}")
            return []  # Return empty list on error
        
# Add to ContentClassificationService class

    def _format_trending_response(self, raw_results):
        """Format trending hashtags response for API consumption"""
        formatted_results = []
        for result in raw_results:
            formatted_results.append({
                "tag": result.get("tag", ""),
                "count": result.get("count", 0),  # Usage count
                "engagement_rate": result.get("engagement_rate", 0.0),
                "velocity": result.get("velocity", 0.0),
                "trend_score": result.get("trend_score", 0.0)
            })
        return formatted_results

    async def get_posts_by_hashtag(self, session: AsyncSession, hashtag: str, skip: int = 0, limit: int = 20):
        """
        Get posts associated with a specific hashtag
        
        Args:
            session: Database session
            hashtag: The hashtag to find posts for
            skip: Number of posts to skip (for pagination)
            limit: Maximum number of posts to return
            
        Returns:
            Dict with posts that contain the specified hashtag
        """
        try:
            from sqlalchemy import func, select
            from app.db.models import Post, User, Hashtag
            from app.db.associated_tables import post_hashtags
            
            # Find the hashtag in the database
            result = await session.execute(
                select(Hashtag).where(Hashtag.tag == hashtag)
            )
            db_hashtag = result.scalars().first()
            
            if not db_hashtag:
                logger.info(f"Hashtag '{hashtag}' not found in database")
                return {"items": [], "total": 0}
            
            # Increment view count for the hashtag
            if db_hashtag.view_count is None:
                db_hashtag.view_count = 1
            else:
                db_hashtag.view_count += 1
            
            # Query for posts with this hashtag
            query = (
                select(Post, User.username)
                .join(post_hashtags, Post.id == post_hashtags.c.post_id)
                .join(User, User.id == Post.author_id)
                .where(post_hashtags.c.hashtag_id == db_hashtag.id)
                .order_by(Post.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            
            result = await session.execute(query)
            post_tuples = result.all()
            
            # Count total posts with this hashtag
            count_query = (
                select(func.count())
                .select_from(post_hashtags)
                .where(post_hashtags.c.hashtag_id == db_hashtag.id)
            )
            
            count_result = await session.execute(count_query)
            total_count = count_result.scalar_one()
            
            # Format the response
            posts = [
                {
                    "id": post.id,
                    "content": post.content,
                    "created_at": post.created_at.isoformat(),
                    "author_username": username,
                    "like_count": post.like_count or 0,
                    "view_count": post.view_count or 0,
                    "repost_count": post.repost_count or 0,
                    "hashtags": await self._extract_hashtags_from_content(post.content)
                }
                for post, username in post_tuples
            ]
            
            await session.commit()  # Commit to save the hashtag view count increment
            
            return {
                "items": posts,
                "total": total_count,
                "hashtag": hashtag
            }
            
        except Exception as e:
            await session.rollback()  # Rollback on error
            logger.error(f"Error getting posts by hashtag: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching posts: {str(e)}"
            )
        
    async def _extract_hashtags_from_content(self, content: str) -> List[str]:
        """Extract hashtags from text content"""
        import re
        pattern = r'#(\w+)'
        matches = re.findall(pattern, content)
        return [tag for tag in matches if len(tag) <= 50 and not any(c.isspace() for c in tag)]

    async def get_topic_distribution(self, session: AsyncSession, topic: str):
        """
        Get distribution of a specific topic in content
        
        Args:
            session: Database session
            topic: The topic to analyze
            
        Returns:
            Topic distribution data
        """
        try:
            # Query MongoDB for topic classifications
            pipeline = [
                {"$match": {"topics.topic": topic}},
                {"$unwind": "$topics"},
                {"$match": {"topics.topic": topic}},
                {"$group": {
                    "_id": None,
                    "avg_confidence": {"$avg": "$topics.confidence"},
                    "count": {"$sum": 1},
                    "post_ids": {"$push": "$post_id"}
                }}
            ]
            
            result = await self.topic_collection.aggregate(pipeline).to_list(None)
            
            if not result:
                return {
                    "topic": topic,
                    "distribution": {"count": 0, "avg_confidence": 0},
                    "related_hashtags": [],
                    "posts": []
                }
                
            distribution = result[0]
            post_ids = distribution.get("post_ids", [])[:10]  # Limit to 10 posts
            
            # Get related hashtags
            hashtag_pipeline = [
                {"$match": {"post_id": {"$in": post_ids}}},
                {"$group": {
                    "_id": "$hashtags",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            
            hashtag_result = await self.mongodb.get_collection("post_metadata").aggregate(hashtag_pipeline).to_list(None)
            related_hashtags = [item["_id"] for item in hashtag_result if item["_id"]]
            
            # Get sample posts
            if post_ids:
                post_query = (
                    select(Post, User.username)
                    .join(User, User.id == Post.author_id)
                    .where(Post.id.in_(post_ids))
                    .limit(5)
                )
                
                post_result = await session.execute(post_query)
                post_tuples = post_result.all()
                
                posts = [
                    {
                        "id": post.id,
                        "content": post.content,
                        "created_at": post.created_at,
                        "author_username": username
                    }
                    for post, username in post_tuples
                ]
            else:
                posts = []
            
            return {
                "topic": topic,
                "distribution": {
                    "count": distribution["count"],
                    "avg_confidence": distribution["avg_confidence"]
                },
                "related_hashtags": related_hashtags,
                "posts": posts
            }
            
        except Exception as e:
            logger.error(f"Error getting topic distribution: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error analyzing topic: {str(e)}"
            )
    async def record_hashtag_view(self, session: AsyncSession, hashtag: str, user_id: int):
        """
        Record a view for a hashtag and increment its view count in the database
        
        Args:
            session: Database session
            hashtag: The hashtag to record a view for
            user_id: ID of the user viewing the hashtag
            
        Returns:
            Dict with success status
        """
        try:
            # First, find the hashtag in the database
            result = await session.execute(
                select(Hashtag).where(Hashtag.tag == hashtag)
            )
            db_hashtag = result.scalars().first()
            
            if not db_hashtag:
                # Hashtag doesn't exist, create it
                db_hashtag = Hashtag(tag=hashtag)
                session.add(db_hashtag)
                await session.flush()
            
            # Increment view count
            if db_hashtag.view_count is None:
                db_hashtag.view_count = 1
            else:
                db_hashtag.view_count += 1
            
            # Update last viewed timestamp
            db_hashtag.last_viewed = datetime.utcnow()
            
            # Track in Redis for rate limiting (one view per user per hour)
            view_key = f"hashtag_view:{hashtag}:{user_id}:{int(datetime.utcnow().timestamp() // 3600)}"
            already_viewed = await self.redis_manager.redis.exists(view_key)
            
            if not already_viewed:
                # Mark as viewed with 1 hour expiration
                await self.redis_manager.redis.setex(view_key, 3600, 1)
                
                # Also track for trending calculations
                await self.trending_collection.insert_one({
                    "type": "hashtag_view",
                    "tag": hashtag,
                    "user_id": user_id,
                    "timestamp": datetime.utcnow()
                })
            
            await session.commit()
            
            return {"success": True, "view_count": db_hashtag.view_count}
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error recording hashtag view: {e}")
            return {"success": False, "error": str(e)}

    async def _parallel_classify(self, content: str) -> Dict:
        """
        Perform parallel content classification using the model manager.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Dictionary with classification results
        """
        # Run all classifications in parallel with timeouts
        try:
            tasks = [
                asyncio.wait_for(self._analyze_sentiment(content), timeout=5.0),
                asyncio.wait_for(self._detect_language(content), timeout=5.0),
                asyncio.wait_for(self._extract_entities(content), timeout=5.0)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results, handling any exceptions
            sentiment = results[0] if not isinstance(results[0], Exception) else {"label": "UNKNOWN", "score": 0.0}
            language = results[1] if not isinstance(results[1], Exception) else {"language": "unknown", "confidence": 0.0}
            entities = results[2] if not isinstance(results[2], Exception) else []
            
            return {
                "sentiment": sentiment,
                "language": language,
                "entities": entities
            }
            
        except Exception as e:
            logger.error(f"Error in parallel classification: {e}")
            # Return default values on error
            return {
                "sentiment": {"label": "UNKNOWN", "score": 0.0},
                "language": {"language": "unknown", "confidence": 0.0},
                "entities": []
            }

    async def _analyze_sentiment(self, content: str) -> Dict:
        """
        Analyze content sentiment using the model manager.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Sentiment analysis results
        """
        try:
            result = await self.model_manager.run_model("sentiment", content)
            return {
                "label": result[0]["label"],
                "score": result[0]["score"]
            }
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return {"label": "UNKNOWN", "score": 0.0}

    async def _moderate_content(self, content: str) -> Dict:
        """
        Check content against moderation rules with caching.
        
        Args:
            content: Text content to moderate
            
        Returns:
            Moderation result dictionary
        """
        try:
            # Generate cache key based on content hash
            content_hash = hashlib.md5(content.encode()).hexdigest()
            cache_key = f"content_moderation:{content_hash}"
            
            # Check cache
            cached_result = await self.redis_manager.get_post(cache_key)
            if cached_result:
                return cached_result

            # If not in cache, perform moderation
            # In a real implementation, this would call an actual content moderation service
            # For now, we'll use a simple placeholder
            result = {
                "is_safe": True,
                "rating": "G",
                "flags": []
            }
            
            # Cache moderation result
            await self.redis_manager.set_post(cache_key, result, ttl=self.moderation_cache_ttl)
            
            return result

        except Exception as e:
            logger.error(f"Error in content moderation: {e}")
            # Default to safe if moderation fails - this is a business decision
            # You might want to fail closed (assume unsafe) instead, depending on your requirements
            return {"is_safe": True, "rating": "G", "flags": []}

    async def _batch_store_hashtags(
        self,
        session: AsyncSession,
        post_id: int,
        hashtags: Set[str]
    ):
        """Store hashtags with batching and increment usage count"""
        if not hashtags:
            return

        # Get or create hashtags in batch
        existing_hashtags = await session.execute(
            select(Hashtag).where(Hashtag.tag.in_(hashtags))
        )
        existing_hashtags = {h.tag: h for h in existing_hashtags.scalars()}
        
        # Create new hashtags or increment usage count
        new_hashtags = []
        for tag in hashtags:
            if tag in existing_hashtags:
                # Increment usage count for existing hashtag
                hashtag = existing_hashtags[tag]
                if hashtag.usage_count is None:
                    hashtag.usage_count = 1
                else:
                    hashtag.usage_count += 1
            else:
                # Create new hashtag with usage_count=1
                new_hashtag = Hashtag(tag=tag, usage_count=1)
                session.add(new_hashtag)
                new_hashtags.append(new_hashtag)
        
        if new_hashtags:
            await session.flush()
            
        # Create associations
        for tag in hashtags:
            hashtag = existing_hashtags.get(tag) or next((h for h in new_hashtags if h.tag == tag), None)
            if hashtag:
                await session.execute(
                    post_hashtags.insert().values(
                        post_id=post_id,
                        hashtag_id=hashtag.id
                    )
                )

    async def _detect_language(self, content: str) -> Dict[str, str]:
        """
        Detect content language using the model manager.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Language detection results
        """
        try:
            result = await self.model_manager.run_model("language", content)
            return {
                "language": result[0]["label"],
                "confidence": result[0]["score"]
            }
        except Exception as e:
            logger.error(f"Error detecting language: {e}")
            return {"language": "unknown", "confidence": 0.0}

    async def _extract_entities(self, content: str) -> List[Dict]:
        """
        Extract named entities from content using the model manager.
        
        Args:
            content: Text content to analyze
            
        Returns:
            List of extracted entities with metadata
        """
        try:
            entities = await self.model_manager.run_model("entity", content)
            
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
        """
        Classify content into topics with confidence scores.
        
        Args:
            content: Text content to analyze
            embedding: Vector embedding of the content
            
        Returns:
            List of topic classifications with confidence scores
        """
        try:
            # Use the model manager to run the topic classifier
            results = await self.model_manager.run_model(
                "topic",
                (content, {"candidate_labels": self.candidate_topics})
            )
            
            # Format results
            topics = [
                {
                    "topic": label,
                    "confidence": score,
                    "related_hashtags": []  # This could be populated from another service
                }
                for label, score in zip(results["labels"], results["scores"])
            ]
            
            return topics

        except Exception as e:
            logger.error(f"Error classifying topics: {e}")
            return []  # Return empty list on error

# Add this to your ContentClassificationService class

    async def debug_trending_metrics(self):
        """
        Diagnostic method to check trending hashtags system status.
        Can be called from an admin endpoint.
        """
        try:
            # Check if collection exists and has documents
            count = await self.trending_collection.count_documents({})
            
            # Get sample documents
            recent_docs = await self.trending_collection.find().sort("timestamp", -1).limit(5).to_list(None)
            
            # Try a simplified aggregation
            simplified_pipeline = [
                {
                    "$match": {
                        "type": "hashtag"
                    }
                },
                {
                    "$group": {
                        "_id": "$tag",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            
            simple_results = await self.trending_collection.aggregate(simplified_pipeline).to_list(None)
            
            # Check for potential calculation issues
            calculation_check = await self.trending_collection.find(
                {"type": "hashtag"}, 
                {"tag": 1, "timestamp": 1, "first_used": 1}
            ).limit(5).to_list(None)
            
            return {
                "collection_status": {
                    "exists": count > 0,
                    "document_count": count,
                    "sample_documents": recent_docs
                },
                "simple_trending": simple_results,
                "calculation_check": calculation_check
            }
        except Exception as e:
            logger.error(f"Error in trending hashtags debug: {e}")
            return {"error": str(e)}