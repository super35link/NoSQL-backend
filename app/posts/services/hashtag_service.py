# app/posts/services/hashtag_service.py
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Any
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.mongodb import get_mongodb
from app.db.qdrant import QdrantManager
from app.db.redis import redis_manager 
from app.db.models import Hashtag, Post, User, post_hashtags
from app.posts.services.embedding_service import PostEmbeddingService

from bson import ObjectId
import json


logger = logging.getLogger(__name__)

class MongoJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles MongoDB specific types"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)  # Convert ObjectId to string
        if isinstance(obj, datetime):
            return obj.isoformat()  # Convert datetime to ISO format string
        return super().default(obj)

def serialize_mongodb_doc(doc):
    """Recursively serialize MongoDB document to JSON-compatible dict"""
    if doc is None:
        return None
    
    if isinstance(doc, list):
        return [serialize_mongodb_doc(item) for item in doc]
        
    if isinstance(doc, dict):
        return {k: serialize_mongodb_doc(v) for k, v in doc.items()}
    
    if isinstance(doc, ObjectId):  # Fixed: Changed 'obj' to 'doc'
        return str(doc)  # Convert ObjectId to string
        
    if isinstance(doc, datetime):
        return doc.isoformat()
        
    return doc
class HashtagService:
    """
    Enhanced hashtag service using MongoDB for dynamic data
    and Qdrant for semantic features.
    """
    def __init__(self):
        # Get database connections
        self.mongodb = get_mongodb()
        self.redis_manager = redis_manager
        self.qdrant = QdrantManager()
        self.embedding_service = PostEmbeddingService()
        
        # Initialize MongoDB collections
        self.hashtag_follows = self.mongodb.get_collection("hashtag_follows")
        self.hashtag_stats = self.mongodb.get_collection("hashtag_stats")
        self.trending_collection = self.mongodb.get_collection("trending_metrics")
        
        # Set default TTLs
        self.trending_cache_ttl = 300  # 5 minutes
        self.user_follows_cache_ttl = 3600  # 1 hour
        
        # Initialize hashtag categories
        self.hashtag_categories = {
            "technology": ["coding", "ai", "programming", "tech", "computer"],
            "health": ["fitness", "wellness", "nutrition", "exercise", "diet"],
            "entertainment": ["movies", "music", "games", "television", "celebrities"],
            "business": ["finance", "startup", "investing", "marketing", "economy"],
            "education": ["learning", "school", "university", "teaching", "student"],
            "politics": ["government", "policy", "election", "democracy", "law"],
            "science": ["research", "biology", "physics", "chemistry", "astronomy"],
            "sports": ["football", "basketball", "soccer", "tennis", "baseball"]
        }
        
    async def _record_hashtag_in_trending(
            self,
            hashtag: str,
            post_id: int = None,
            user_id: int = None,
            engagement_value: float = 1.0
        ) -> None:
            """
            Record hashtag usage for trending analytics
            
            Args:
                hashtag: The hashtag used (without #)
                post_id: Optional post ID that used the hashtag
                user_id: Optional user ID who created the post
                engagement_value: Value to assign to this usage (higher for posts, lower for views)
            """
            try:
                now = datetime.utcnow()
                normalized_tag = hashtag.lower().strip('#')
                
                # Record in trending collection
                await self.trending_collection.insert_one({
                    "type": "hashtag",
                    "tag": normalized_tag,
                    "post_id": post_id,
                    "user_id": user_id,
                    "timestamp": now,
                    "engagement_value": engagement_value
                })
                
                # Update hashtag stats
                await self.hashtag_stats.update_one(
                    {"tag": normalized_tag},
                    {
                        "$inc": {"usage_count": 1},
                        "$set": {"last_used": now},
                        "$setOnInsert": {
                            "first_seen": now,
                            "category": await self._classify_hashtag(normalized_tag)
                        }
                    },
                    upsert=True
                )
                
                # Update user-hashtag relationship if user provided
                if user_id:
                    await self.hashtag_follows.update_one(
                        {
                            "user_id": user_id,
                            "hashtag": normalized_tag
                        },
                        {
                            "$set": {"last_interaction": now},
                            "$inc": {"engagement_level": 0.5},  # Using hashtag is higher engagement than viewing
                            "$push": {
                                "recent_interactions": {
                                    "type": "used",
                                    "timestamp": now,
                                    "post_id": post_id
                                }
                            }
                        },
                        upsert=False  # Only update if the user already follows this hashtag
                    )
            except Exception as e:
                logger.error(f"Error recording hashtag usage: {e}")
                # Log the error but don't re-raise to prevent affecting post creation
    
    # ==========================================
    # Follow Management Methods
    # ==========================================
    
    async def follow_hashtag(self, user_id: int, hashtag: str) -> Dict:
        """
        Follow a hashtag with rich engagement metadata
        
        Args:
            user_id: User ID following the hashtag
            hashtag: Hashtag to follow (without #)
            
        Returns:
            Dict with status and follow info
        """
        try:
            # Normalize hashtag (lowercase, no #)
            normalized_tag = hashtag.lower().strip()
            if normalized_tag.startswith('#'):
                normalized_tag = normalized_tag[1:]
                
            # Validate hashtag
            if not normalized_tag or len(normalized_tag) > 50:
                return {"success": False, "error": "Invalid hashtag format"}
            
            # Check if already followed
            existing = await self.hashtag_follows.find_one({
                "user_id": user_id,
                "hashtag": normalized_tag
            })
            
            if existing:
                return {"success": True, "already_following": True}
            
            # Insert new follow record
            now = datetime.utcnow()
            follow_record = {
                "user_id": user_id,
                "hashtag": normalized_tag,
                "followed_at": now,
                "engagement_level": 0,
                "last_interaction": now,
                "recent_interactions": []
            }
            
            result = await self.hashtag_follows.insert_one(follow_record)
            
            # Update hashtag stats (create if not exists)
            await self.hashtag_stats.update_one(
                {"tag": normalized_tag},
                {
                    "$inc": {"follower_count": 1},
                    "$set": {"last_follow": now},
                    "$setOnInsert": {
                        "first_seen": now,
                        "category": await self._classify_hashtag(normalized_tag)
                    }
                },
                upsert=True
            )
            
            # Invalidate cache
            follow_cache_key = f"user_follows:{user_id}"
            await self.redis_manager.delete_key(follow_cache_key)
            
            return {
                "success": True,
                "hashtag": normalized_tag,
                "followed_at": now,
                "already_following": False
            }
            
        except Exception as e:
            logger.error(f"Error following hashtag: {e}")
            return {"success": False, "error": str(e)}
    
    async def unfollow_hashtag(self, user_id: int, hashtag: str) -> Dict:
        """
        Unfollow a hashtag
        
        Args:
            user_id: User ID unfollowing the hashtag
            hashtag: Hashtag to unfollow (without #)
            
        Returns:
            Dict with status and unfollow info
        """
        try:
            # Normalize hashtag (lowercase, no #)
            normalized_tag = hashtag.lower().strip()
            if normalized_tag.startswith('#'):
                normalized_tag = normalized_tag[1:]
            
            # Remove from follows collection
            result = await self.hashtag_follows.delete_one({
                "user_id": user_id,
                "hashtag": normalized_tag
            })
            
            if result.deleted_count == 0:
                return {"success": True, "was_following": False}
            
            # Decrement follower count in stats
            await self.hashtag_stats.update_one(
                {"tag": normalized_tag},
                {"$inc": {"follower_count": -1}}
            )
            
            # Invalidate cache
            follow_cache_key = f"user_follows:{user_id}"
            await self.redis_manager.delete_key(follow_cache_key)
            
            return {
                "success": True,
                "hashtag": normalized_tag,
                "was_following": True
            }
                
        except Exception as e:
            logger.error(f"Error unfollowing hashtag: {e}")
            return {"success": False, "error": str(e)}
    
    
    async def get_followed_hashtags(self, user_id: int, limit: int = 100) -> List[Dict]:
        """
        Get all hashtags followed by a user with rich metadata
        
        Args:
            user_id: User ID to get follows for
            limit: Maximum number of follows to return
            
        Returns:
            List of followed hashtags with metadata
        """
        try:
            # Check cache first
            cache_key = f"user_follows:{user_id}"
            cached_follows = await self.redis_manager.get_post(cache_key)
            if cached_follows:
                return cached_follows
            
            # Query MongoDB for follows
            cursor = self.hashtag_follows.find(
                {"user_id": user_id},
                sort=[("last_interaction", -1)],
                limit=limit
            )
            
            follows = await cursor.to_list(length=None)
            
            # Enrich with additional hashtag data
            if follows:
                hashtags = [follow["hashtag"] for follow in follows]
                stats = await self._get_hashtags_stats(hashtags)
                
                # Merge stats into follows
                for follow in follows:
                    tag = follow["hashtag"]
                    if tag in stats:
                        follow["stats"] = stats[tag]
            
            # Serialize MongoDB documents to JSON-compatible dicts
            serialized_follows = serialize_mongodb_doc(follows)
            
            # Cache the result
            await self.redis_manager.set_post(
                cache_key,
                serialized_follows,
                ttl=self.user_follows_cache_ttl
            )
            
            return serialized_follows
            
        except Exception as e:
            logger.error(f"Error getting followed hashtags: {e}")
            return []

    
    async def check_follows_hashtags(
        self,
        user_id: int,
        hashtags: List[str]
    ) -> Dict[str, bool]:
        """
        Check if user follows multiple hashtags
        
        Args:
            user_id: User ID to check
            hashtags: List of hashtags to check
            
        Returns:
            Dict mapping hashtags to follow status
        """
        try:
            # Normalize hashtags
            normalized_tags = [
                tag.lower().strip('#') for tag in hashtags
            ]
            
            # Query MongoDB for follows
            results = await self.hashtag_follows.find(
                {
                    "user_id": user_id,
                    "hashtag": {"$in": normalized_tags}
                },
                projection={"hashtag": 1}
            ).to_list(None)
            
            # Create result dict with all hashtags initially set to False
            follow_status = {tag: False for tag in normalized_tags}
            
            # Update status for followed hashtags
            for result in results:
                follow_status[result["hashtag"]] = True
            
            return follow_status
            
        except Exception as e:
            logger.error(f"Error checking hashtag follows: {e}")
            return {tag: False for tag in hashtags}
            
    # ==========================================
    # Trending and Discovery Methods
    # ==========================================
    
    async def get_trending_hashtags(
        self,
        timeframe: str = "24h",
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        Get trending hashtags with rich metrics
        
        Args:
            timeframe: Time period ("1h", "24h", "7d", "30d")
            category: Optional category filter
            limit: Maximum results to return
            offset: Number of results to skip
            
        Returns:
            Dict with trending hashtags and metadata
        """
        try:
            # Input validation
            valid_timeframes = {"1h", "24h", "7d", "30d"}
            if timeframe not in valid_timeframes:
                timeframe = "24h"
            
            # Check cache if no offset
            if offset == 0:
                cache_key = f"trending_hashtags:{timeframe}:{limit}"
                if category:
                    cache_key += f":{category}"
                    
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
            
            # Build MongoDB aggregation pipeline
            pipeline = [
                # Match documents in the timeframe
                {
                    "$match": {
                        "timestamp": {"$gte": time_threshold},
                        "type": "hashtag"
                    }
                }
            ]
            
            # Add category filter if provided
            if category and category in self.hashtag_categories:
                pipeline.append({
                    "$match": {
                        "tag": {"$in": self.hashtag_categories[category]}
                    }
                })
            
            # Continue with aggregation
            pipeline.extend([
                # Group by tag
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
                # Apply pagination
                {"$skip": offset},
                {"$limit": limit},
                # Final projection
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
            ])
            
            # Execute aggregation with timeout
            try:
                raw_results = await asyncio.wait_for(
                    self.trending_collection.aggregate(pipeline).to_list(None),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.error("Timeout executing trending hashtags pipeline")
                return {"items": [], "total": 0}
            
            # Get total count with a separate query
            count_pipeline = pipeline.copy()
            # Remove pagination and projection
            count_pipeline = count_pipeline[:-3]
            count_pipeline.append({"$count": "total"})
            
            try:
                count_result = await asyncio.wait_for(
                    self.trending_collection.aggregate(count_pipeline).to_list(None),
                    timeout=3.0
                )
                total = count_result[0]["total"] if count_result else len(raw_results)
            except (asyncio.TimeoutError, IndexError):
                logger.warning("Error getting trending hashtags count")
                total = len(raw_results)
            
            # Enrich with additional hashtag data
            enriched_results = []
            for result in raw_results:
                hashtag = result["tag"]
                
                # Get hashtag metadata
                stats = await self.hashtag_stats.find_one({"tag": hashtag})
                
                enriched_item = {
                    **result,
                    "follower_count": stats.get("follower_count", 0) if stats else 0,
                    "category": stats.get("category") if stats else None
                }
                enriched_results.append(enriched_item)
            
            # Format the response
            response = {
                "items": enriched_results,
                "total": total,
                "timeframe": timeframe,
                "category": category
            }
            
            # Cache the response if no offset
            if offset == 0:
                await self.redis_manager.set_post(
                    cache_key,
                    response,
                    ttl=self.trending_cache_ttl
                )
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting trending hashtags: {e}")
            return {"items": [], "total": 0}
    
    async def get_hashtag_categories(self) -> Dict[str, List[str]]:
        """Get available hashtag categories with examples"""
        return self.hashtag_categories
    
    async def get_posts_by_hashtag(
        self,
        session: AsyncSession,
        hashtag: str,
        skip: int = 0,
        limit: int = 20
    ):
        """
        Get posts associated with a specific hashtag
        """
        try:
            # Normalize hashtag
            normalized_tag = hashtag.lower().strip('#')
            
            # Find the hashtag in the database
            result = await session.execute(
                select(Hashtag).where(Hashtag.tag == normalized_tag)
            )
            db_hashtag = result.scalars().first()
            
            if not db_hashtag:
                logger.info(f"Hashtag '{normalized_tag}' not found in database")
                return {"items": [], "total": 0}
            
            # Increment view count in MongoDB for trending stats
            await self._record_hashtag_view(normalized_tag)
            
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
            posts = []
            for post, username in post_tuples:
                # Extract hashtags from content
                post_hashtags_list = await self._extract_hashtags_from_content(post.content)
                
                posts.append({
                    "id": post.id,
                    "content": post.content,
                    "created_at": post.created_at.isoformat(),
                    "author_username": username,
                    "like_count": post.like_count or 0,
                    "view_count": post.view_count or 0,
                    "repost_count": post.repost_count or 0,
                    "hashtags": post_hashtags_list
                })
            
            # Get hashtag stats from MongoDB
            stats = await self.hashtag_stats.find_one({"tag": normalized_tag}) or {}
            
            # Get related hashtags from embedding service
            related_hashtags = await self.find_related_hashtags(normalized_tag, 5)
            related_tags = [item["tag"] for item in related_hashtags]
            
            return {
                "items": posts,
                "total": total_count,
                "hashtag": normalized_tag,
                "follower_count": stats.get("follower_count", 0),
                "category": stats.get("category"),
                "related_hashtags": related_tags
            }
            
        except Exception as e:
            logger.error(f"Error getting posts by hashtag: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching posts: {str(e)}"
            )
    
    async def find_related_hashtags(
        self,
        hashtag: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Find semantically related hashtags using vector similarity
        
        Args:
            hashtag: Seed hashtag to find related tags
            limit: Maximum number of results
            
        Returns:
            List of related hashtags with similarity scores
        """
        try:
            # Normalize hashtag
            normalized_tag = hashtag.lower().strip('#')
            
            # Generate embedding for the hashtag
            embedding = await self.embedding_service.generate_embedding(f"#{normalized_tag}")
            if not embedding:
                return []
            
            # Search for similar content in Qdrant
            search_results = await self.qdrant.search_similar_posts(
                query_vector=embedding,
                filter_conditions={"hashtags": [normalized_tag]},
                limit=limit * 5,  # Get more to compensate for filtering
                score_threshold=0.7
            )
            
            if not search_results:
                return []
            
            # Extract hashtags from results and calculate frequencies
            hashtag_freq = {}
            for result in search_results:
                metadata = result.get("metadata", {})
                post_hashtags = metadata.get("hashtags", [])
                
                for tag in post_hashtags:
                    if tag != normalized_tag:
                        hashtag_freq[tag] = hashtag_freq.get(tag, 0) + 1
            
            # Convert to sorted list
            related_hashtags = [
                {"tag": tag, "frequency": freq, "score": freq / len(search_results)}
                for tag, freq in hashtag_freq.items()
            ]
            
            # Sort by frequency and limit
            related_hashtags.sort(key=lambda x: x["frequency"], reverse=True)
            related_hashtags = related_hashtags[:limit]
            
            # Enrich with additional metadata
            if related_hashtags:
                tags = [item["tag"] for item in related_hashtags]
                stats = await self._get_hashtags_stats(tags)
                
                for item in related_hashtags:
                    tag = item["tag"]
                    if tag in stats:
                        item["stats"] = stats[tag]
            
            serialized_hashtags = serialize_mongodb_doc(related_hashtags)
            return serialized_hashtags
            
        except Exception as e:
            logger.error(f"Error finding related hashtags: {e}")
            return []
    
    async def suggest_hashtags(
        self,
        content: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Suggest hashtags for content based on semantic similarity
        
        Args:
            content: Text content to suggest hashtags for
            limit: Maximum number of suggestions
            
        Returns:
            List of suggested hashtags with confidence scores
        """
        try:
            # Generate embedding for the content
            embedding = await self.embedding_service.generate_embedding(content)
            if not embedding:
                return []
            
            # Search for similar content in Qdrant
            search_results = await self.qdrant.search_similar_posts(
                query_vector=embedding,
                limit=limit * 3,  # Get more to compensate for filtering
                score_threshold=0.75
            )
            
            if not search_results:
                return []
            
            # Extract hashtags from results and calculate weighted scores
            hashtag_scores = {}
            for result in search_results:
                similarity = result.get("score", 0)
                metadata = result.get("metadata", {})
                post_hashtags = metadata.get("hashtags", [])
                
                for tag in post_hashtags:
                    current_score = hashtag_scores.get(tag, 0)
                    # Weight by similarity score
                    hashtag_scores[tag] = current_score + similarity
            
            # Convert to sorted list
            suggested_hashtags = [
                {"tag": tag, "score": score}
                for tag, score in hashtag_scores.items()
            ]
            
            # Sort by score and limit
            suggested_hashtags.sort(key=lambda x: x["score"], reverse=True)
            suggested_hashtags = suggested_hashtags[:limit]
            
            return suggested_hashtags
            
        except Exception as e:
            logger.error(f"Error suggesting hashtags: {e}")
            return []
    
    # ==========================================
    # Helper Methods
    # ==========================================
    
    async def _get_hashtags_stats(self, hashtags: List[str]) -> Dict[str, Dict]:
        """Get stats for multiple hashtags"""
        try:
            cursor = self.hashtag_stats.find(
                {"tag": {"$in": hashtags}}
            )
            
            results = await cursor.to_list(length=None)
            
            # Convert to dictionary keyed by tag
            return {
                result["tag"]: {
                    "follower_count": result.get("follower_count", 0),
                    "category": result.get("category"),
                    "first_seen": result.get("first_seen")
                }
                for result in results
            }
            
        except Exception as e:
            logger.error(f"Error getting hashtags stats: {e}")
            return {}
    
    async def _extract_hashtags_from_content(self, content: str) -> List[str]:
        """Extract hashtags from text content"""
        import re
        pattern = r'#(\w+)'
        matches = re.findall(pattern, content)
        return [tag for tag in matches if len(tag) <= 50 and not any(c.isspace() for c in tag)]
    
    async def _classify_hashtag(self, hashtag: str) -> Optional[str]:
        """Classify hashtag into a category"""
        for category, tags in self.hashtag_categories.items():
            if hashtag in tags:
                return category
                
        # Try semantic classification
        try:
            embedding = await self.embedding_service.generate_embedding(f"#{hashtag}")
            if not embedding:
                return None
                
            # TODO: Implement semantic classification with category embeddings
            # For now, return None
            
            return None
            
        except Exception:
            return None
    
    async def _record_hashtag_view(
        self,
        hashtag: str,
        user_id: Optional[int] = None
    ) -> None:
        """Record a view of a hashtag"""
        try:
            now = datetime.utcnow()
            
            # Update hashtag stats
            await self.hashtag_stats.update_one(
                {"tag": hashtag.lower()},
                {
                    "$inc": {"view_count": 1},
                    "$set": {"last_viewed": now},
                    "$setOnInsert": {
                        "first_seen": now
                    }
                },
                upsert=True
            )
            
            # Record in trending collection
            await self.trending_collection.insert_one({
                "type": "hashtag_view",
                "tag": hashtag.lower(),
                "user_id": user_id,
                "timestamp": now,
                "engagement_value": 0.5  # Views are worth less than uses
            })
            
            # Update user-hashtag follow relationship if applicable
            if user_id:
                await self.hashtag_follows.update_one(
                    {
                        "user_id": user_id,
                        "hashtag": hashtag.lower()
                    },
                    {
                        "$set": {"last_interaction": now},
                        "$inc": {"engagement_level": 0.1},
                        "$push": {
                            "recent_interactions": {
                                "type": "view",
                                "timestamp": now
                            }
                        }
                    }
                )
        except Exception as e:
            logger.error(f"Error recording hashtag view: {e}")