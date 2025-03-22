import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func
from sqlalchemy.orm import joinedload, contains_eager
from typing import Dict, Literal, Optional, List, Set
from datetime import datetime
import logging
from fastapi import HTTPException, status
from pydantic import ValidationError
import json

from app.db.associated_tables import post_hashtags, post_mentions
from app.db.models import Hashtag, Post, User
from app.db.redis import RedisManager
from app.posts.schemas.post_schemas import PostCreate, PostUpdate, PostResponse
from app.posts.services.embedding_service import PostEmbeddingService
from app.posts.services.hashtag_service import HashtagService  # Import HashtagService

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class PostCache:
    """Handle post caching operations"""
    def __init__(self, redis_manager: RedisManager, cache_ttl: int = 3600):
        self.redis_manager = redis_manager
        self.cache_ttl = cache_ttl

    async def get_post(self, post_id: int) -> Optional[Dict]:
        """Get post from cache"""
        try:
            key = f"post:{post_id}"
            # Use the RedisManager's redis property
            data = await self.redis_manager.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis error getting post {post_id}: {e}")
            return None

    async def set_post(self, post_id: int, post_data: Dict):
        """Cache post data"""
        try:
            key = f"post:{post_id}"
            # Use custom encoder for datetime objects
            serialized_data = json.dumps(post_data, cls=DateTimeEncoder)
            await self.redis_manager.redis.setex(
                key,
                self.cache_ttl,
                serialized_data
            )
        except Exception as e:
            logger.error(f"Redis error setting post {post_id}: {e}")

    async def invalidate_post(self, post_id: int):
        """Remove post from cache"""
        try:
            key = f"post:{post_id}"
            await self.redis_manager.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis error invalidating post {post_id}: {e}")

class PostValidator:
    """Validate post content and metadata"""
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
    
    async def _contains_inappropriate_content(self, content: str) -> bool:
        # Placeholder for content moderation logic
        return False
    
    async def validate_content(self, content: str) -> bool:
        """Validate post content"""
        if not content or len(content.strip()) == 0:
            raise ValidationError("Post content cannot be empty")
        
        if len(content) > 500:
            raise ValidationError("Post content exceeds maximum length")
            
        # Add content moderation check
        if await self._contains_inappropriate_content(content):
            raise ValidationError("Post contains inappropriate content")
            
        return True

    async def validate_rate_limit(self, user_id: int) -> bool:
        """Check if user has exceeded post rate limit"""
        try:
            window_key = f"post_rate:{user_id}:{int(datetime.utcnow().timestamp() // 3600)}"
            
            # Use the redis_manager's check_rate_limit method
            if not await self.redis_manager.check_rate_limit(
                key=window_key,
                limit=100,  # 100 posts per hour limit
                window_seconds=3600
            ):
                raise ValidationError("Post rate limit exceeded")
                
            return True
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Rate limit check failed: %s", str(e))
            return True  # Fail open on errors

class EnhancedCorePostService:
    """Enhanced post service with caching and validation"""
    def __init__(self, cache: PostCache, validator: PostValidator):
        self.cache = cache
        self.validator = validator
        # Use the redis_manager from cache instead of creating a new one
        self.redis_manager = cache.redis_manager
        # Initialize HashtagService for MongoDB integration
        self.hashtag_service = HashtagService()
        
    async def create_post(
        self, 
        session: AsyncSession, 
        user_id: int, 
        post_data: PostCreate
    ) -> PostResponse:
        """Create a new post with validation, embedding generation, and caching"""
        # Validate user exists
        user = await self._get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate content and rate limit
        await self.validator.validate_content(post_data.content)
        await self.validator.validate_rate_limit(user_id)

        # Extract hashtags and mentions
        hashtags = await self._extract_entities(session, post_data.content, "hashtag")
        mentioned_user_ids = await self._extract_entities(session, post_data.content, "mention")

        # First transaction: Create the post and store hashtags in the database
        try:
            # Create post instance
            post = Post(
                author_id=user_id,
                content=post_data.content,
                reply_to_id=post_data.reply_to_id
            )

            session.add(post)
            # Flush to get ID but don't commit yet
            await session.flush()
            
            # Store hashtags and mentions
            await self._batch_store_hashtags(session, post.id, hashtags)
            await self._batch_store_mentions(session, post.id, mentioned_user_ids)
            
            # CRITICAL: Commit the database transaction to ensure hashtags are stored
            # even if embedding generation fails
            await session.commit()
            await session.refresh(post)
            
            # Prepare response
            response = PostResponse(
                id=post.id,
                content=post.content,
                created_at=post.created_at,
                author_username=user.username,
                author_id=user_id,
                reply_to_id=post.reply_to_id,
                like_count=0,
                view_count=0,
                repost_count=0,
                hashtags=list(hashtags) if hashtags else []
            )
            
            # Cache the new post
            try:
                post_dict = response.dict()
                await self.cache.set_post(post.id, post_dict)
            except Exception as e:
                logger.warning(f"Failed to cache post: {e}")
                # Don't let caching errors affect the main workflow
            
            # Second operation: Generate and store embedding
            # This is now outside the main database transaction
            try:
                embedding_service = PostEmbeddingService()
                await embedding_service.process_post(
                    post_id=post.id,
                    content=post.content,
                    metadata={
                        "author_id": user_id,
                        "created_at": post.created_at.isoformat(),
                        "hashtags": list(hashtags) if hashtags else []
                    }
                )
            except Exception as e:
                # Log the error but don't fail the whole operation
                logger.error(f"Error generating embedding: {e}")
                # The post is already committed, so we don't need to roll back
            
            # NEW: Process hashtags in MongoDB for trending metrics and analytics
            # Do this after the main transaction is committed
            try:
                if hashtags:
                    # Process each hashtag in MongoDB
                    for tag in hashtags:
                        await self._record_hashtag_in_mongodb(
                            tag=tag,
                            post_id=post.id,
                            user_id=user_id
                        )
                    logger.info(f"Processed {len(hashtags)} hashtags in MongoDB for post {post.id}")
            except Exception as e:
                # Log the error but don't fail the operation since the post is already created
                logger.error(f"Error processing hashtags in MongoDB: {e}")
                
            return response

        except Exception as e:
            # Only roll back if we haven't committed yet
            try:
                await session.rollback()
            except:
                pass
            logger.error(f"Error creating post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create post"
            )

    async def _record_hashtag_in_mongodb(
        self,
        tag: str,
        post_id: int,
        user_id: int
    ) -> None:
        """Record hashtag usage in MongoDB for trending analytics"""
        try:
            # Use HashtagService to record hashtag in trending metrics
            await self.hashtag_service._record_hashtag_in_trending(
                hashtag=tag,
                post_id=post_id,
                user_id=user_id,
                engagement_value=1.0  # New posts have higher engagement value
            )
            
            # Check if user follows this hashtag and update engagement if they do
            # This helps with personalized recommendations
            follows = await self.hashtag_service.check_follows_hashtags(
                user_id=user_id,
                hashtags=[tag]
            )
            
            if follows.get(tag, False):
                # User is following this hashtag, update follow engagement
                await self.hashtag_service.hashtag_follows.update_one(
                    {
                        "user_id": user_id,
                        "hashtag": tag
                    },
                    {
                        "$set": {"last_interaction": datetime.utcnow()},
                        "$inc": {"engagement_level": 0.5},  # Using a followed hashtag shows high engagement
                        "$push": {
                            "recent_interactions": {
                                "type": "used",
                                "timestamp": datetime.utcnow(),
                                "post_id": post_id
                            }
                        }
                    }
                )
        except Exception as e:
            logger.error(f"Error recording hashtag {tag} in MongoDB: {e}")
            # Don't re-raise to ensure post creation succeeds even if MongoDB fails

    async def update_post(
        self, 
        session: AsyncSession, 
        user_id: int, 
        post_id: int, 
        post_data: PostUpdate
    ) -> PostResponse:
        """Update a post with cache invalidation"""
        # Validate content if provided
        if post_data.content:
            await self.validator.validate_content(post_data.content)

        # Get existing post and verify ownership
        post = await self.get_post(session, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
            
        # Verify ownership
        result = await session.execute(
            select(Post).where(Post.id == post_id)
        )
        db_post = result.scalar_one()
        if db_post.author_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this post")

        try:
            # Extract new hashtags and mentions if content is updated
            old_hashtags = set()
            new_hashtags = set()
            
            if post_data.content:
                # Get existing hashtags before clearing
                result = await session.execute(
                    select(Hashtag.tag)
                    .join(post_hashtags, post_hashtags.c.hashtag_id == Hashtag.id)
                    .where(post_hashtags.c.post_id == post_id)
                )
                old_hashtags = {row[0] for row in result}
                
                # Clear existing hashtags and mentions
                post_id_column = post_hashtags.columns.get('post_id')
                mention_id_column = post_mentions.columns.get('post_id')
                
                await session.execute(
                    delete(post_hashtags).where(post_id_column == post_id)
                )
                await session.execute(
                    delete(post_mentions).where(mention_id_column == post_id)
                )
                # Extract and store new hashtags and mentions
                new_hashtags = await self._extract_entities(session, post_data.content, "hashtag")
                mentioned_user_ids = await self._extract_entities(session, post_data.content, "mention")
                
                await self._batch_store_hashtags(session, post_id, new_hashtags)
                await self._batch_store_mentions(session, post_id, mentioned_user_ids)

            # Update post content
            db_post.content = post_data.content or db_post.content
            db_post.updated_at = datetime.utcnow()
            
            await session.commit()
            await session.refresh(db_post)
            
            # Invalidate cache
            await self.cache.invalidate_post(post_id)
            
            # NEW: Update MongoDB hashtag records if hashtags changed
            if post_data.content and (old_hashtags != new_hashtags):
                try:
                    # Remove post from old hashtags that were removed
                    removed_hashtags = old_hashtags - new_hashtags
                    for tag in removed_hashtags:
                        await self._remove_hashtag_from_post(tag, post_id, user_id)
                    
                    # Add new hashtags that weren't in the old post
                    added_hashtags = new_hashtags - old_hashtags
                    for tag in added_hashtags:
                        await self._record_hashtag_in_mongodb(tag, post_id, user_id)
                except Exception as e:
                    logger.error(f"Error updating MongoDB hashtag records: {e}")
                    # Don't re-raise since the main update is already committed
            
            # Return updated post
            return PostResponse(
                id=db_post.id,
                content=db_post.content,
                created_at=db_post.created_at,
                author_username=(await self._get_user(session, user_id)).username,
                reply_to_id=db_post.reply_to_id,
                hashtags=list(new_hashtags) if new_hashtags else list(old_hashtags)
            )

        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update post"
            )

    async def _remove_hashtag_from_post(
        self,
        tag: str,
        post_id: int,
        user_id: int
    ) -> None:
        """Remove hashtag-post association in MongoDB"""
        try:
            # This is a soft removal that marks the hashtag as removed from the post
            # Keeping historic data for analytics but marking it as inactive
            await self.hashtag_service.trending_collection.insert_one({
                "type": "hashtag_removal",
                "tag": tag.lower(),
                "post_id": post_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "engagement_value": 0  # Zero engagement since it's removed
            })
        except Exception as e:
            logger.error(f"Error removing hashtag {tag} from post in MongoDB: {e}")

    async def delete_post(
        self,
        session: AsyncSession,
        user_id: int,
        post_id: int
    ) -> bool:
        """Delete a post with cache invalidation"""
        # Get post to verify ownership
        post = await self.get_post(session, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Get existing hashtags before deleting
        try:
            result = await session.execute(
                select(Hashtag.tag)
                .join(post_hashtags, post_hashtags.c.hashtag_id == Hashtag.id)
                .where(post_hashtags.c.post_id == post_id)
            )
            post_hashtags_list = {row[0] for row in result}
        except Exception:
            post_hashtags_list = set()

        result = await session.execute(
            select(Post).where(Post.id == post_id)
        )
        db_post = result.scalar_one()
        
        if db_post.author_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to delete this post"
            )

        try:
            await session.delete(db_post)
            await session.commit()
            
            # Invalidate cache
            await self.cache.invalidate_post(post_id)
            
            # Invalidate user's post count cache
            await self.cache.invalidate_post(f"post_count:{user_id}")
            
            # NEW: Update MongoDB hashtag records for deleted post
            if post_hashtags_list:
                try:
                    for tag in post_hashtags_list:
                        await self._record_hashtag_deletion(tag, post_id, user_id)
                except Exception as e:
                    logger.error(f"Error updating MongoDB for deleted post hashtags: {e}")
            
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete post"
            )

    async def _record_hashtag_deletion(
        self,
        tag: str,
        post_id: int,
        user_id: int
    ) -> None:
        """Record the deletion of a post with this hashtag in MongoDB"""
        try:
            # Record post deletion for this hashtag
            await self.hashtag_service.trending_collection.insert_one({
                "type": "post_deletion",
                "tag": tag.lower(),
                "post_id": post_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "engagement_value": -1.0  # Negative engagement for deletion
            })
        except Exception as e:
            logger.error(f"Error recording hashtag {tag} deletion in MongoDB: {e}")

    async def get_post(
        self, 
        session: AsyncSession, 
        post_id: int
    ) -> Optional[PostResponse]:
        """Get a post with caching"""
        # Try cache first
        cached_post = await self.redis_manager.get_post(post_id)
        if cached_post:
            return PostResponse(**cached_post)
            
        # If not in cache, query database
        try:
            # Execute query
            stmt = (
                select(Post, User.username)
                .join(User, User.id == Post.author_id)
                .where(Post.id == post_id)
            )
            
            result = await session.execute(stmt)
            post_tuple = result.first()  # Get the first result as a tuple

            if not post_tuple:
                return None

            post, username = post_tuple
            
            # Get hashtags for this post
            hashtags_result = await session.execute(
                select(Hashtag.tag)
                .join(post_hashtags, post_hashtags.c.hashtag_id == Hashtag.id)
                .where(post_hashtags.c.post_id == post_id)
            )
            hashtags = [row[0] for row in hashtags_result]
            
            response = PostResponse(
                id=post.id,
                content=post.content,
                created_at=post.created_at,
                author_username=username,
                reply_to_id=post.reply_to_id,
                like_count=post.like_count or 0,
                view_count=post.view_count or 0,
                repost_count=post.repost_count or 0,
                hashtags=hashtags
            )
            
            return response

        except Exception as e:
            logger.error(f"Error getting post {post_id}: {e}")
            return None

    async def get_posts_by_cursor(
        self,
        session: AsyncSession,
        cursor: Optional[datetime] = None,
        limit: int = 20,
        user_id: Optional[int] = None
    ) -> Dict:
        """Get paginated posts using cursor-based pagination"""
        try:
            # Build base query
            query = select(Post).options(joinedload(Post.author))
            
            if user_id:
                query = query.where(Post.author_id == user_id)
            
            # Add cursor condition if provided
            if cursor:
                query = query.where(Post.created_at < cursor)
            
            # Get posts
            result = await session.execute(
                query.order_by(Post.created_at.desc())
                .limit(limit + 1)  # Get one extra to check if there are more
            )
            
            posts = result.unique().scalars().all()
            
            if not posts:
                return {
                    "items": [],
                    "next_cursor": None,
                    "has_more": False
                }
            
            # Determine if there are more posts
            has_more = len(posts) > limit
            if has_more:
                posts = posts[:-1]  # Remove the extra post
            
            # Get the next cursor
            next_cursor = posts[-1].created_at if posts and has_more else None
            
            # Get hashtags for the posts
            post_ids = [post.id for post in posts]
            hashtags_result = await session.execute(
                select(post_hashtags.c.post_id, Hashtag.tag)
                .join(Hashtag, post_hashtags.c.hashtag_id == Hashtag.id)
                .where(post_hashtags.c.post_id.in_(post_ids))
            )
            
            # Group hashtags by post_id
            post_hashtags_map = {}
            for post_id, tag in hashtags_result:
                if post_id not in post_hashtags_map:
                    post_hashtags_map[post_id] = []
                post_hashtags_map[post_id].append(tag)
            
            return {
                "items": [
                    PostResponse(
                        id=post.id,
                        content=post.content,
                        created_at=post.created_at,
                        author_username=post.author.username,
                        reply_to_id=post.reply_to_id,
                        like_count=post.like_count or 0,
                        view_count=post.view_count or 0, 
                        repost_count=post.repost_count or 0,
                        hashtags=post_hashtags_map.get(post.id, [])
                    ) for post in posts
                ],
                "next_cursor": next_cursor.isoformat() if next_cursor else None,
                "has_more": has_more
            }

        except Exception as e:
            logger.error(f"Error fetching posts: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch posts"
            )

    async def get_user_post_count(
        self,
        session: AsyncSession,
        user_id: int
    ) -> int:
        """Get total number of posts for a user with caching"""
        try:
            # Check cache first
            cache_key = f"post_count:{user_id}"
            cached_count = await self.redis_manager.get_counter(cache_key)
            if cached_count is not None:
                return cached_count
            
            # Query database if not in cache
            result = await session.execute(
                select(func.count())
                .select_from(Post)
                .where(Post.author_id == user_id)
            )
            count = result.scalar_one()
            
            # Cache the result
            await self.redis_manager.set_post(cache_key, count)
            
            return count
        except Exception as e:
            logger.error(f"Error getting user post count: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get post count"
            )

    async def bulk_delete_posts(
        self,
        session: AsyncSession,
        user_id: int,
        post_ids: List[int]
    ) -> Dict[str, List[int]]:
        """Bulk delete multiple posts with transaction"""
        if not post_ids:
            raise HTTPException(
                status_code=400,
                detail="No post IDs provided"
            )

        try:
            # Get hashtags for all posts before deleting
            hashtags_by_post = {}
            try:
                result = await session.execute(
                    select(post_hashtags.c.post_id, Hashtag.tag)
                    .join(Hashtag, post_hashtags.c.hashtag_id == Hashtag.id)
                    .where(post_hashtags.c.post_id.in_(post_ids))
                )
                for post_id, tag in result:
                    if post_id not in hashtags_by_post:
                        hashtags_by_post[post_id] = []
                    hashtags_by_post[post_id].append(tag)
            except Exception:
                # Continue even if we can't get hashtags
                pass

            # Verify ownership of all posts first
            result = await session.execute(
                select(Post)
                .where(Post.id.in_(post_ids))
            )
            posts = result.scalars().all()
            
            if not posts:
                raise HTTPException(
                    status_code=404,
                    detail="No posts found with provided IDs"
                )
            
            unauthorized_ids = [
                post.id for post in posts 
                if post.author_id != user_id
            ]
            
            if unauthorized_ids:
                raise HTTPException(
                    status_code=403,
                    detail=f"Not authorized to delete posts: {unauthorized_ids}"
                )

            # Delete posts in a single operation
            await session.execute(
                delete(Post)
                .where(Post.id.in_(post_ids))
            )
            
            # Invalidate cache for each post
            for post_id in post_ids:
                await self.cache.invalidate_post(post_id)
            
            await session.commit()
            
            # Invalidate user's post count cache
            await self.cache.invalidate_post(f"post_count:{user_id}")
            
            # Update MongoDB hashtag records for deleted posts
            try:
                for post_id, tags in hashtags_by_post.items():
                    for tag in tags:
                        await self._record_hashtag_deletion(tag, post_id, user_id)
            except Exception as e:
                logger.error(f"Error updating MongoDB for bulk deleted posts: {e}")
            
            return {
                "deleted": post_ids,
                "failed": []
            }
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error in bulk delete: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to bulk delete posts"
            )

    async def _extract_entities(
            self,
            session: AsyncSession,
            content: str, 
            entity_type: Literal["hashtag", "mention"]
        ) -> Set[str] | Set[int]:  # Return type can be either Set[str] for hashtags or Set[int] for mentions
            """Extract and validate entities (hashtags, mentions) from content"""
            patterns = {
                "hashtag": r'#(\w+)',
                "mention": r'@(\w+)'
            }
            
            if entity_type not in patterns:
                raise ValueError(f"Unsupported entity type: {entity_type}")
            
            pattern = patterns[entity_type]
            matches: List[str] = re.findall(pattern, content)

            if not matches:
                return set()
            
            if entity_type == "hashtag":
                return {
                    tag.lower() for tag in matches  # Normalize hashtags to lowercase
                    if len(tag) <= 50 and not any(c.isspace() for c in tag)
                }
            
            # Handle user mentions
            try:
                result = await session.execute(
                    select(User)
                    .where(User.username.in_(matches))
                )
                valid_users = result.scalars().all()
                
                return {user.id for user in valid_users}
            
            except Exception as e:
                logger.error(f"Error extracting mentions from content: {e}")
                return set()

    async def _batch_store_hashtags(
        self,
        session: AsyncSession,
        post_id: int,
        hashtags: Set[str]
    ) -> None:
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
            hashtag = existing_hashtags.get(tag) or next((h for h in new_hashtags if h.tag == tag), None)
            if hashtag:
                await session.execute(
                    post_hashtags.insert().values(
                        post_id=post_id,
                        hashtag_id=hashtag.id
                    )
                )


    async def _batch_store_mentions(
            self,
            session: AsyncSession,
            post_id: int,
            mentions: Set[int]  # Changed type hint to match actual usage
        ) -> None:
            """Store mentions with batching"""
            if not mentions:
                return
            
            # Create mention associations
            for user_id in mentions:
                await session.execute(
                    post_mentions.insert().values(
                        post_id=post_id,
                        user_id=user_id
                    )
                )

    async def _get_user(self, session: AsyncSession, user_id: int) -> Optional[User]:
        """Get user with caching"""
        # Try cache first
        cached_user = await self.cache.get_post(f"user:{user_id}")
        if cached_user:
            return User(**cached_user)
            
        result = await session.get(User, user_id)
        if result:
            # Here we need to extract only serializable attributes
            user_dict = {
                "id": result.id,
                "username": result.username,
                "email": result.email,
                "is_active": result.is_active,
                "is_superuser": result.is_superuser,
                "is_verified": result.is_verified,
                "first_name": result.first_name,
                "last_name": result.last_name,
                "created_at": result.created_at.isoformat() if result.created_at else None,
                "updated_at": result.updated_at.isoformat() if result.updated_at else None
            }
            # Now cache only the serializable dict
            await self.cache.set_post(f"user:{user_id}", user_dict)
        return result