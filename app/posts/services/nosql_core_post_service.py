from typing import List, Optional, Dict, Any, Union, TypeVar
from datetime import datetime
from bson import ObjectId
from fastapi import HTTPException, status
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection


from app.db.mongodb import get_mongodb
from app.posts.schemas.post_document import PostDocument, PostEngagementDocument, PostInteractionDocument, PostClassificationDocument

logger = logging.getLogger(__name__)

# Type variables for better type annotations
T = TypeVar('T', bound=Dict[str, Any])

class NoSQLCorePostService:
    """
    MongoDB implementation of the core post service.
    Uses MongoDB's native ObjectId instead of PostgreSQL sequences.
    Maintains all functionality of the original service.
    """
    
    def __init__(self):
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.posts_collection: Optional[AsyncIOMotorCollection] = None
        self.engagements_collection: Optional[AsyncIOMotorCollection] = None
        self.interactions_collection: Optional[AsyncIOMotorCollection] = None
        self.classifications_collection: Optional[AsyncIOMotorCollection] = None
    
    async def initialize(self) -> None:
        """Initialize MongoDB collections."""
        self.db = await get_mongodb()
        
        # Explicitly type the collections using annotations
        # This tells the type checker these are AsyncIOMotorCollection objects
        self.posts_collection = self.db["posts"]  # type: AsyncIOMotorCollection
        self.engagements_collection = self.db["post_engagements"]  # type: AsyncIOMotorCollection
        self.interactions_collection = self.db["post_interactions"]  # type: AsyncIOMotorCollection
        self.classifications_collection = self.db["post_classifications"]  # type: AsyncIOMotorCollection
        
        # Ensure indexes are created
        await self._ensure_indexes()
    
    async def _ensure_db(self) -> None:
        """Ensure database connection is initialized."""
        if not self.db:
            await self.initialize()
    
    async def _ensure_indexes(self) -> None:
        """Ensure all necessary indexes are created."""
        if not self.posts_collection:
            await self._ensure_db()
            return
            
        # Posts collection indexes
        await self.posts_collection.create_index("author_id")
        await self.posts_collection.create_index("created_at")
        await self.posts_collection.create_index("reply_to_id")
        await self.posts_collection.create_index("hashtags")
        await self.posts_collection.create_index([("content", "text")])
        
        # Compound indexes for efficient queries
        await self.posts_collection.create_index([("author_id", 1), ("created_at", -1)])
        await self.posts_collection.create_index([("is_deleted", 1), ("is_hidden", 1)])
    
    async def create_post(self, 
                         author_id: int, 
                         content: str, 
                         reply_to_id: Optional[str] = None,
                         hashtags: Optional[List[str]] = None,
                         media_urls: Optional[List[str]] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a new post in MongoDB.
        Returns the string representation of the ObjectId.
        """
        await self._ensure_db()
        
        now = datetime.utcnow()
        
        # Convert reply_to_id to ObjectId if provided
        reply_to_obj = None
        if reply_to_id:
            try:
                reply_to_obj = ObjectId(reply_to_id)
            except Exception as e:
                logger.error(f"Invalid reply_to_id format: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid reply_to_id format"
                )
        
        # Create post document
        post_doc: PostDocument = {
            "_id": ObjectId(),
            "author_id": author_id,
            "content": content,
            "created_at": now,
            "updated_at": None,
            "likes_count": 0,
            "views_count": 0,
            "reposts_count": 0,
            "reply_to_id": reply_to_obj,
            "hashtags": hashtags or [],
            "media_urls": media_urls or [],
            "is_deleted": False,
            "is_hidden": False,
            "engagement_score": 0.0,
            "metadata": metadata or {}
        }
        
        # Insert post document
        result = await self.posts_collection.insert_one(post_doc)  # type: ignore
        post_id = str(result.inserted_id)
        
        # Initialize engagement document
        engagement_doc: PostEngagementDocument = {
            "post_id": result.inserted_id,
            "likes_count": 0,
            "views_count": 0,
            "reposts_count": 0,
            "comments_count": 0,
            "shares_count": 0,
            "last_updated": now,
            "engagement_score": 0.0
        }
        
        # Insert engagement document
        await self.engagements_collection.insert_one(engagement_doc)  # type: ignore
        
        return post_id
    
    async def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a post by its ID.
        Converts ObjectId to string in the returned document.
        """
        await self._ensure_db()
        
        try:
            post_id_obj = ObjectId(post_id)
        except Exception as e:
            logger.error(f"Invalid post_id format: {e}")
            return None
        
        post = await self.posts_collection.find_one({"_id": post_id_obj})  # type: ignore
        
        if post:
            # Convert ObjectId to string for JSON serialization
            post["_id"] = str(post["_id"])
            if post.get("reply_to_id"):
                post["reply_to_id"] = str(post["reply_to_id"])
            
            # Get engagement metrics
            engagement = await self.engagements_collection.find_one({"post_id": post_id_obj})  # type: ignore
            if engagement:
                post["engagement"] = {
                    "likes_count": engagement.get("likes_count", 0),
                    "views_count": engagement.get("views_count", 0),
                    "reposts_count": engagement.get("reposts_count", 0),
                    "comments_count": engagement.get("comments_count", 0),
                    "shares_count": engagement.get("shares_count", 0)
                }
        
        return post
    
    async def update_post(self, 
                         post_id: str, 
                         content: Optional[str] = None,
                         hashtags: Optional[List[str]] = None,
                         media_urls: Optional[List[str]] = None,
                         is_hidden: Optional[bool] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update a post by its ID.
        Returns True if successful, False otherwise.
        """
        await self._ensure_db()
        
        try:
            post_id_obj = ObjectId(post_id)
        except Exception as e:
            logger.error(f"Invalid post_id format: {e}")
            return False
        
        # Build update document
        update_doc = {"updated_at": datetime.utcnow()}
        
        if content is not None:
            update_doc["content"] = content
        
        if hashtags is not None:
            update_doc["hashtags"] = hashtags
        
        if media_urls is not None:
            update_doc["media_urls"] = media_urls
        
        if is_hidden is not None:
            update_doc["is_hidden"] = is_hidden
        
        if metadata is not None:
            update_doc["metadata"] = metadata
        
        # Update post
        result = await self.posts_collection.update_one(  # type: ignore
            {"_id": post_id_obj, "is_deleted": False},
            {"$set": update_doc}
        )
        
        return result.modified_count > 0
    
    async def delete_post(self, post_id: str) -> bool:
        """
        Soft delete a post by its ID.
        Returns True if successful, False otherwise.
        """
        await self._ensure_db()
        
        try:
            post_id_obj = ObjectId(post_id)
        except Exception as e:
            logger.error(f"Invalid post_id format: {e}")
            return False
        
        # Soft delete post
        result = await self.posts_collection.update_one(  # type: ignore
            {"_id": post_id_obj},
            {"$set": {"is_deleted": True, "updated_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    
    async def get_posts_by_author(self, 
                                 author_id: int, 
                                 skip: int = 0, 
                                 limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get posts by author ID with pagination.
        Returns a list of posts with ObjectId converted to string.
        """
        await self._ensure_db()
        
        cursor = self.posts_collection.find(  # type: ignore
            {"author_id": author_id, "is_deleted": False, "is_hidden": False}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        posts = []
        async for post in cursor:
            # Convert ObjectId to string for JSON serialization
            post["_id"] = str(post["_id"])
            if post.get("reply_to_id"):
                post["reply_to_id"] = str(post["reply_to_id"])
            posts.append(post)
        
        return posts
    
    async def get_post_replies(self, 
        post_id: str, 
        skip: int = 0, 
        limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get replies to a post with pagination.
        Returns a list of posts with ObjectId converted to string.
        """
        await self._ensure_db()
        
        try:
            post_id_obj = ObjectId(post_id)
        except Exception as e:
            logger.error(f"Invalid post_id format: {e}")
            return []
        
        cursor = self.posts_collection.find(  # type: ignore
            {"reply_to_id": post_id_obj, "is_deleted": False, "is_hidden": False}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        replies = []
        async for reply in cursor:
            # Convert ObjectId to string for JSON serialization
            reply["_id"] = str(reply["_id"])
            reply["reply_to_id"] = str(reply["reply_to_id"])
            replies.append(reply)
        
        return replies
    
    async def record_interaction(self, 
                                post_id: str, 
                                user_id: int, 
                                interaction_type: str,
                                metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Record a user interaction with a post.
        Returns True if successful, False otherwise.
        """
        await self._ensure_db()
        
        try:
            post_id_obj = ObjectId(post_id)
        except Exception as e:
            logger.error(f"Invalid post_id format: {e}")
            return False
        
        # Check if post exists
        post = await self.posts_collection.find_one({"_id": post_id_obj, "is_deleted": False})  # type: ignore
        if not post:
            return False
        
        # Record interaction
        interaction_doc: PostInteractionDocument = {
            "user_id": user_id,
            "post_id": post_id_obj,
            "interaction_type": interaction_type,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {}
        }
        
        await self.interactions_collection.insert_one(interaction_doc)  # type: ignore
        
        # Update engagement metrics
        update_field = f"{interaction_type}_count"
        
        await self.engagements_collection.update_one(  # type: ignore
            {"post_id": post_id_obj},
            {
                "$inc": {update_field: 1},
                "$set": {"last_updated": datetime.utcnow()}
            },
            upsert=True
        )
        
        # Update post metrics for quick access
        if interaction_type in ["like", "view", "repost"]:
            update_field = f"{interaction_type}s_count"  # likes_count, views_count, reposts_count
            
            await self.posts_collection.update_one(  # type: ignore
                {"_id": post_id_obj},
                {"$inc": {update_field: 1}}
            )
        
        return True
    
    async def search_posts(self, 
        query: str, 
        skip: int = 0, 
        limit: int = 20) -> List[Dict[str, Any]]:
        
        """ Search posts by text content. Returns a list of posts with ObjectId converted to string."""
        
        await self._ensure_db()
        
        cursor = self.posts_collection.find(  # type: ignore
            {
                "$text": {"$search": query},
                "is_deleted": False,
                "is_hidden": False
            },
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)
        
        posts = []
        async for post in cursor:
            # Convert ObjectId to string for JSON serialization
            post["_id"] = str(post["_id"])
            if post.get("reply_to_id"):
                post["reply_to_id"] = str(post["reply_to_id"])
            posts.append(post)
        
        return posts
    
    async def get_posts_by_hashtag(self, 
        hashtag: str, 
        skip: int = 0, 
        limit: int = 20) -> List[Dict[str, Any]]:
        
        """ Get posts by hashtag with pagination. Returns a list of posts with ObjectId converted to string."""
        await self._ensure_db()
        
        cursor = self.posts_collection.find(  # type: ignore
            {"hashtags": hashtag, "is_deleted": False, "is_hidden": False}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        posts = []
        async for post in cursor:
            # Convert ObjectId to string for JSON serialization
            post["_id"] = str(post["_id"])
            if post.get("reply_to_id"):
                post["reply_to_id"] = str(post["reply_to_id"])
            posts.append(post)
        
        return posts
    
    async def add_post_classification(self, 
            post_id: str, 
            topics: List[Dict[str, Union[str, float]]],
            sentiment: Optional[Dict[str, float]] = None) -> bool:
        
            """ Add content classification to a post. Returns True if successful, False otherwise."""
            
            await self._ensure_db()
            
            try:
                post_id_obj = ObjectId(post_id)
            except Exception as e:
                logger.error(f"Invalid post_id format: {e}")
                return False
            
            # Check if post exists
            post = await self.posts_collection.find_one({"_id": post_id_obj})  # type: ignore
            if not post:
                return False
            
            now = datetime.utcnow()
            
            # Create classification document
            classification_doc: PostClassificationDocument = {
                "post_id": post_id_obj,
                "topics": topics,
                "sentiment": sentiment,
                "created_at": now,
                "updated_at": None
            }
            
            # Insert or update classification
            await self.classifications_collection.update_one(  # type: ignore
                {"post_id": post_id_obj},
                {"$set": classification_doc},
                upsert=True
            )
            
            return True
        

    async def get_post_classification(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get content classification for a post.
        Returns classification data with ObjectId converted to string.
        """
        await self._ensure_db()
        
        try:
            post_id_obj = ObjectId(post_id)
        except Exception as e:
            logger.error(f"Invalid post_id format: {e}")
            return None
        
        classification = await self.classifications_collection.find_one({"post_id": post_id_obj})  # type: ignore
        
        if classification:
            # Convert ObjectId to string for JSON serialization
            classification["post_id"] = str(classification["post_id"])
        
        return classification