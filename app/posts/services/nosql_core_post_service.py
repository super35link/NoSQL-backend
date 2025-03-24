from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timedelta
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, List, Optional, Union, TypedDict, cast, Any
import asyncio
import re
import logging

from app.db.mongodb_cache_manager import MongoDBCacheManager


from app.core.config import settings
from app.posts.schemas.post_schemas import PostCreate, PostUpdate, PostResponse
from app.posts.services.embedding_service import PostEmbeddingService
from app.posts.services.hashtag_service import HashtagService

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class PostDocument(TypedDict):
    _id: Union[ObjectId, str]
    author_id: int
    content: str
    created_at: datetime
    updated_at: datetime
    hashtags: List[str]
    mentioned_users: List[int]
    like_count: int
    view_count: int
    repost_count: int
    is_deleted: bool
    is_hidden: bool
    is_edited: bool
    reply_to_id: Optional[str]
    repost_of: Optional[str]


class LikeDocument(TypedDict):
    post_id: str
    user_id: int
    created_at: datetime


class MentionDocument(TypedDict):
    mentioned_user_id: int
    post_id: str
    author_id: int
    created_at: datetime


class NotificationDocument(TypedDict):
    user_id: int
    actor_id: int
    post_id: str
    type: str
    read: bool
    created_at: datetime


class UserActivityDocument(TypedDict):
    user_id: int
    activity_type: str
    target_id: Optional[str]
    created_at: datetime


class UserDocument(TypedDict):
    user_id: int
    username: str
    display_name: str
    email: str
    avatar: Optional[str]
    follower_count: int
    following_count: int
    created_at: datetime


class MongoDBPostService:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DB_NAME]
        
        # Correct way to access collections
        self.posts_collection = self.db["posts"]
        self.likes_collection = self.db["post_likes"]
        self.mentions_collection = self.db["mentions"]
        self.notifications_collection = self.db["notifications"]
        self.activities_collection = self.db["user_activities"]
        self.users_collection = self.db["users"]
        
        self.cache_manager = MongoDBCacheManager()
        self.embedding_service = PostEmbeddingService()
        self.hashtag_service = HashtagService()
        
        # Setup indexes
        asyncio.create_task(self._setup_indexes())
        
    async def _setup_indexes(self) -> None:
        # Create indexes for performance
        await self.posts_collection.create_index("author_id")  # For user's posts
        await self.posts_collection.create_index("created_at")  # For timeline sorting
        await self.posts_collection.create_index("hashtags")  # For hashtag searches
        await self.posts_collection.create_index("mentioned_users")  # For mention searches
        await self.posts_collection.create_index([("content", "text")])  # Text search
        await self.posts_collection.create_index("reply_to_id")  # For thread retrieval
        await self.posts_collection.create_index([("author_id", 1), ("created_at", -1)])  # For user timeline
        
        # Indexes for other collections
        await self.likes_collection.create_index([("post_id", 1), ("user_id", 1)], unique=True)
        await self.mentions_collection.create_index("mentioned_user_id")
        await self.notifications_collection.create_index([("user_id", 1), ("read", 1)])
        await self.activities_collection.create_index([("user_id", 1), ("created_at", -1)])
        
    async def create_post(self, user_id: int, post_data: PostCreate) -> PostResponse:
        """Create a new post with validation, embedding generation, and caching"""
        # Validate user exists
        user = await self._get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Validate content and rate limit
        await self._validate_content(post_data.content)
        await self._check_rate_limit(user_id)
        
        # Extract hashtags and mentions
        hashtags = self._extract_hashtags(post_data.content)
        mentioned_users = await self._extract_mentions(post_data.content)
        
        # Create post document with MongoDB ObjectId
        current_time = datetime.utcnow()
        post: PostDocument = {
            "_id": ObjectId(),  # MongoDB will generate this automatically
            "author_id": user_id,
            "content": post_data.content,
            "reply_to_id": post_data.reply_to_id,
            "created_at": current_time,
            "updated_at": current_time,
            "hashtags": hashtags,
            "mentioned_users": mentioned_users,
            "like_count": 0,
            "view_count": 0,
            "repost_count": 0,
            "is_deleted": False,
            "is_hidden": False,
            "is_edited": False,
            "repost_of": post_data.repost_of
        }
        
        # Insert into MongoDB
        result = await self.posts_collection.insert_one(post)
        post_id = str(result.inserted_id)
        
        # Process hashtags in MongoDB for trending
        for tag in hashtags:
            await self._record_hashtag(tag, post_id, user_id)
            
        # Process mentions and create notifications
        for mentioned_user_id in mentioned_users:
            await self._record_mention(mentioned_user_id, post_id, user_id)
            await self._create_mention_notification(mentioned_user_id, user_id, post_id)
            
        # Generate embedding
        try:
            await self.embedding_service.process_post(
                post_id=post_id,
                content=post_data.content,
                metadata={
                    "author_id": user_id,
                    "created_at": current_time.isoformat(),
                    "hashtags": hashtags
                }
            )
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            
        # Cache the post
        post_copy = post.copy()
        post_copy["_id"] = post_id  # Convert ObjectId to string for caching
        await self.cache_manager.set_post(post_id, post_copy)
        
        # Record user activity
        await self._record_user_activity(user_id, "post_created", post_id)
        
        # Prepare response
        user_doc = cast(UserDocument, user)
        response = PostResponse(
            id=post_id,
            content=post_data.content,
            created_at=current_time,
            author_username=user_doc["username"],
            author_id=user_id,
            reply_to_id=post_data.reply_to_id,
            like_count=0,
            view_count=0,
            repost_count=0,
            hashtags=hashtags
        )
        
        return response
        
    async def get_post(self, post_id: str) -> Optional[PostResponse]:
        """Get a post by ID with caching"""
        # Try cache first
        cached_post = await self.cache_manager.get_post(post_id)
        if cached_post:
            return self._convert_to_response(cast(PostDocument, cached_post))
            
        # Get from MongoDB
        try:
            object_id = ObjectId(post_id)
            post = await self.posts_collection.find_one({"_id": object_id, "is_deleted": False})
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return None
        
        if not post:
            return None
            
        # Increment view count
        await self.increment_view_count(post_id)
            
        # Cache if found
        if post:
            post_doc = cast(PostDocument, post)
            post_copy = post_doc.copy()
            post_copy["_id"] = post_id  # Convert ObjectId to string for caching
            await self.cache_manager.set_post(post_id, post_copy)
            
        return self._convert_to_response(cast(PostDocument, post))
        
    async def update_post(self, post_id: str, user_id: int, update_data: PostUpdate) -> Optional[PostResponse]:
        """Update a post with validation and cache invalidation"""
        # Check post exists and user is author
        try:
            object_id = ObjectId(post_id)
            post = await self.posts_collection.find_one({"_id": object_id, "author_id": user_id, "is_deleted": False})
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return None
            
        if not post:
            return None
            
        # Validate content if provided
        if update_data.content:
            await self._validate_content(update_data.content)
            
        # Update fields
        update: Dict[str, Any] = {
            "$set": {
                "updated_at": datetime.utcnow(),
                "is_edited": True
            }
        }
        
        # Extract new hashtags and mentions if content changed
        if update_data.content:
            # Validate content
            await self._validate_content(update_data.content)
            
            # Extract entities
            hashtags = self._extract_hashtags(update_data.content)
            mentioned_users = await self._extract_mentions(update_data.content)
            
            # Update post content and entities
            update["$set"]["content"] = update_data.content
            update["$set"]["hashtags"] = hashtags
            update["$set"]["mentioned_users"] = mentioned_users
            
            post_doc = cast(PostDocument, post)
            
            # Process new hashtags
            old_hashtags = set(post_doc.get("hashtags", []))
            new_hashtags = set(hashtags)
            
            # Add new hashtags
            for tag in new_hashtags - old_hashtags:
                await self._record_hashtag(tag, post_id, user_id)
                
            # Process new mentions
            old_mentions = set(post_doc.get("mentioned_users", []))
            new_mentions = set(mentioned_users)
            
            # Create notifications for new mentions
            for mentioned_user_id in new_mentions - old_mentions:
                await self._record_mention(mentioned_user_id, post_id, user_id)
                await self._create_mention_notification(mentioned_user_id, user_id, post_id)
                
            # Update embedding
            try:
                current_time = datetime.utcnow()
                await self.embedding_service.process_post(
                    post_id=post_id,
                    content=update_data.content,
                    metadata={
                        "author_id": user_id,
                        "created_at": post_doc["created_at"].isoformat(),
                        "updated_at": current_time.isoformat(),
                        "hashtags": hashtags
                    }
                )
            except Exception as e:
                logger.error(f"Error updating embedding: {e}")
            
        # Update in MongoDB
        await self.posts_collection.update_one({"_id": object_id}, update)
        
        # Invalidate cache
        await self.cache_manager.invalidate_post(post_id)
        
        # Record user activity
        await self._record_user_activity(user_id, "post_updated", post_id)
        
        # Return updated post
        return await self.get_post(post_id)
        
    async def delete_post(self, post_id: str, user_id: int) -> bool:
        """Soft delete a post"""
        # Check post exists and user is author
        try:
            object_id = ObjectId(post_id)
            post = await self.posts_collection.find_one({"_id": object_id, "author_id": user_id, "is_deleted": False})
            
            if not post:
                return False
                
            # Soft delete
            await self.posts_collection.update_one(
                {"_id": object_id},
                {"$set": {"is_deleted": True, "deleted_at": datetime.utcnow()}}
            )
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return False
        
        # Invalidate cache
        await self.cache_manager.invalidate_post(post_id)
        
        # Record user activity
        await self._record_user_activity(user_id, "post_deleted", post_id)
        
        return True
        
    async def get_user_posts(self, user_id: int, limit: int = 20, skip: int = 0) -> List[PostResponse]:
        """Get posts by a specific user"""
        cursor = self.posts_collection.find({"author_id": user_id, "is_deleted": False})
        cursor = cursor.sort("created_at", -1).skip(skip).limit(limit)
        posts = await cursor.to_list(length=limit)
        
        return [self._convert_to_response(cast(PostDocument, post)) for post in posts]
        
    async def get_post_replies(self, post_id: str, limit: int = 20, skip: int = 0) -> List[PostResponse]:
        """Get replies to a specific post"""
        try:
            # Note: We're using the string post_id directly here since reply_to_id is stored as a string
            cursor = self.posts_collection.find({"reply_to_id": post_id, "is_deleted": False})
            cursor = cursor.sort("created_at", 1).skip(skip).limit(limit)
            posts = await cursor.to_list(length=limit)
            
            return [self._convert_to_response(cast(PostDocument, post)) for post in posts]
        except Exception as e:
            logger.error(f"Error getting post replies: {e}")
            return []
        
    async def get_thread(self, post_id: str) -> List[PostResponse]:
        """Get the full thread containing a post"""
        # Get the target post
        try:
            object_id = ObjectId(post_id)
            post = await self.posts_collection.find_one({"_id": object_id, "is_deleted": False})
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return []
            
        if not post:
            return []
            
        thread_posts: List[Dict[str, Any]] = []
        post_doc = cast(PostDocument, post)
        
        # If this is a reply, get the parent posts recursively
        if post_doc.get("reply_to_id"):
            parent_posts = await self._get_parent_posts(post_doc.get("reply_to_id", ""))
            thread_posts.extend(parent_posts)
            
        # Add the target post
        thread_posts.append(post_doc)
        
        # Get direct replies
        replies = await self.get_post_replies(post_id, limit=100)
        thread_posts.extend([reply.dict() for reply in replies])
        
        # Sort by created_at
        thread_posts.sort(key=lambda x: x.get("created_at"))
        
        return [self._convert_to_response(cast(PostDocument, post)) for post in thread_posts]
        
    async def _get_parent_posts(self, post_id: str, collected: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Recursively get parent posts"""
        if collected is None:
            collected = []
            
        try:
            object_id = ObjectId(post_id)
            post = await self.posts_collection.find_one({"_id": object_id, "is_deleted": False})
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return collected
            
        if not post:
            return collected
            
        post_doc = cast(PostDocument, post)
        
        # If this post has a parent, get it first
        if post_doc.get("reply_to_id"):
            await self._get_parent_posts(post_doc.get("reply_to_id", ""), collected)
            
        # Add this post
        collected.append(post_doc)
        return collected
        
    async def like_post(self, post_id: str, user_id: int) -> bool:
        """Like a post"""
        # Check if post exists
        try:
            object_id = ObjectId(post_id)
            post = await self.posts_collection.find_one({"_id": object_id, "is_deleted": False})
            
            if not post:
                return False
                
            # Check if already liked
            like = await self.likes_collection.find_one({"post_id": post_id, "user_id": user_id})
            if like:
                return False
                
            # Add like
            like_doc: LikeDocument = {
                "post_id": post_id,
                "user_id": user_id,
                "created_at": datetime.utcnow()
            }
            await self.likes_collection.insert_one(like_doc)
            
            # Increment like count
            await self.posts_collection.update_one(
                {"_id": object_id},
                {"$inc": {"like_count": 1}}
            )
            
            post_doc = cast(PostDocument, post)
            
            # Create notification for post author
            if post_doc["author_id"] != user_id:
                await self._create_like_notification(post_doc["author_id"], user_id, post_id)
                
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return False
        
        # Invalidate cache
        await self.cache_manager.invalidate_post(post_id)
        
        # Record user activity
        await self._record_user_activity(user_id, "post_liked", post_id)
        
        return True
        
    async def unlike_post(self, post_id: str, user_id: int) -> bool:
        """Unlike a post"""
        # Check if liked
        result = await self.likes_collection.delete_one({"post_id": post_id, "user_id": user_id})
        
        if result.deleted_count == 0:
            return False
            
        # Decrement like count
        try:
            object_id = ObjectId(post_id)
            await self.posts_collection.update_one(
                {"_id": object_id},
                {"$inc": {"like_count": -1}}
            )
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return False
        
        # Invalidate cache
        await self.cache_manager.invalidate_post(post_id)
        
        # Record user activity
        await self._record_user_activity(user_id, "post_unliked", post_id)
        
        return True
        
    async def repost(self, post_id: str, user_id: int, content: Optional[str] = None) -> Optional[PostResponse]:
        """Repost or quote a post"""
        # Check if post exists
        try:
            object_id = ObjectId(post_id)
            original_post = await self.posts_collection.find_one({"_id": object_id, "is_deleted": False})
            
            if not original_post:
                return None
                
            # Create repost data
            repost_data = PostCreate(
                content=content or "",
                repost_of=post_id
            )
            
            # Create the repost
            repost = await self.create_post(user_id, repost_data)
            
            # Update repost count on original
            await self.posts_collection.update_one(
                {"_id": object_id},
                {"$inc": {"repost_count": 1}}
            )
            
            original_post_doc = cast(PostDocument, original_post)
            
            # Create notification for original post author
            if original_post_doc["author_id"] != user_id:
                await self._create_repost_notification(original_post_doc["author_id"], user_id, post_id)
                
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return None
        
        # Invalidate cache for original post
        await self.cache_manager.invalidate_post(post_id)
        
        return repost
        
    async def increment_view_count(self, post_id: str) -> bool:
        """Increment post view count"""
        try:
            object_id = ObjectId(post_id)
            result = await self.posts_collection.update_one(
                {"_id": object_id, "is_deleted": False},
                {"$inc": {"view_count": 1}}
            )
            return result.modified_count > 0
        except InvalidId:
            logger.error(f"Invalid ObjectId format: {post_id}")
            return False
        
    async def search_posts(self, query: str, limit: int = 20, skip: int = 0) -> List[PostResponse]:
        """Search posts by content"""
        cursor = self.posts_collection.find(
            {"$text": {"$search": query}, "is_deleted": False},
            {"score": {"$meta": "textScore"}}
        )
        cursor = cursor.sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)
        posts = await cursor.to_list(length=limit)
        
        return [self._convert_to_response(cast(PostDocument, post)) for post in posts]
        
    async def get_posts_by_hashtag(self, hashtag: str, limit: int = 20, skip: int = 0) -> List[PostResponse]:
        """Get posts with a specific hashtag"""
        cursor = self.posts_collection.find({"hashtags": hashtag, "is_deleted": False})
        cursor = cursor.sort("created_at", -1).skip(skip).limit(limit)
        posts = await cursor.to_list(length=limit)
        
        return [self._convert_to_response(cast(PostDocument, post)) for post in posts]
        
    async def get_trending_hashtags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get trending hashtags"""
        return await self.hashtag_service.get_trending_hashtags(limit)
        
    # Helper methods
    async def _get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user from MongoDB"""
        return await self.users_collection.find_one({"user_id": user_id})
        
    async def _validate_content(self, content: str) -> bool:
        """Validate post content"""
        if not content or len(content.strip()) == 0:
            raise ValidationError("Post content cannot be empty")
            
        if len(content) > 500:
            raise ValidationError("Post content exceeds maximum length")
            
        # Add content moderation check here
        if await self._contains_inappropriate_content(content):
            raise ValidationError("Post contains inappropriate content")
            
        return True
        
    async def _contains_inappropriate_content(self, content: str) -> bool:
        """Check for inappropriate content"""
        # Placeholder for content moderation logic
        return False
        
    async def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user has exceeded post rate limit"""
        # Get posts in the last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        count = await self.posts_collection.count_documents({
            "author_id": user_id,
            "created_at": {"$gte": one_hour_ago}
        })
        
        if count >= 100:  # 100 posts per hour limit
            raise ValidationError("Post rate limit exceeded")
            
        return True
        
    def _extract_hashtags(self, content: str) -> List[str]:
        """Extract hashtags from content"""
        hashtag_pattern = r'#(\w+)'
        matches = re.findall(hashtag_pattern, content)
        return [tag.lower() for tag in matches]
        
    async def _extract_mentions(self, content: str) -> List[int]:
        """Extract mentioned user IDs from content"""
        mention_pattern = r'@(\w+)'
        usernames = re.findall(mention_pattern, content)
        
        user_ids: List[int] = []
        for username in usernames:
            user = await self.users_collection.find_one({"username": username})
            if user:
                user_doc = cast(UserDocument, user)
                user_ids.append(user_doc["user_id"])
                
        return user_ids
        
    async def _record_hashtag(self, tag: str, post_id: str, user_id: int) -> None:
        """Record hashtag usage"""
        await self.hashtag_service.record_hashtag_usage(tag, post_id, user_id)
        
    async def _record_mention(self, mentioned_user_id: int, post_id: str, author_id: int) -> None:
        """Record user mention"""
        mention_doc: MentionDocument = {
            "mentioned_user_id": mentioned_user_id,
            "post_id": post_id,
            "author_id": author_id,
            "created_at": datetime.utcnow()
        }
        await self.mentions_collection.insert_one(mention_doc)
        
    async def _create_mention_notification(self, user_id: int, actor_id: int, post_id: str) -> None:
        """Create notification for mentioned user"""
        notification_doc: NotificationDocument = {
            "user_id": user_id,
            "actor_id": actor_id,
            "post_id": post_id,
            "type": "mention",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await self.notifications_collection.insert_one(notification_doc)
        
    async def _create_like_notification(self, user_id: int, actor_id: int, post_id: str) -> None:
        """Create notification for post like"""
        notification_doc: NotificationDocument = {
            "user_id": user_id,
            "actor_id": actor_id,
            "post_id": post_id,
            "type": "like",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await self.notifications_collection.insert_one(notification_doc)
        
    async def _create_repost_notification(self, user_id: int, actor_id: int, post_id: str) -> None:
        """Create notification for repost"""
        notification_doc: NotificationDocument = {
            "user_id": user_id,
            "actor_id": actor_id,
            "post_id": post_id,
            "type": "repost",
            "read": False,
            "created_at": datetime.utcnow()
        }
        await self.notifications_collection.insert_one(notification_doc)
        
    async def _record_user_activity(self, user_id: int, activity_type: str, target_id: Optional[str] = None) -> None:
        """Record user activity"""
        activity_doc: UserActivityDocument = {
            "user_id": user_id,
            "activity_type": activity_type,
            "target_id": target_id,
            "created_at": datetime.utcnow()
        }
        await self.activities_collection.insert_one(activity_doc)
        
    def _convert_to_response(self, post: PostDocument) -> PostResponse:
        """Convert MongoDB post document to PostResponse"""
        return PostResponse(
            id=str(post["_id"]),
            content=post["content"],
            created_at=post["created_at"],
            updated_at=post.get("updated_at"),
            author_id=post["author_id"],
            author_username="",  # This would need to be populated
            reply_to_id=post.get("reply_to_id"),
            repost_of=post.get("repost_of"),
            like_count=post.get("like_count", 0),
            view_count=post.get("view_count", 0),
            repost_count=post.get("repost_count", 0),
            hashtags=post.get("hashtags", []),
            is_edited=post.get("is_edited", False)
        )
