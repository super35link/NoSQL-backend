import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func
from sqlalchemy.orm import joinedload, contains_eager
from typing import Dict, Literal, Optional, List, Set
from datetime import datetime
import logging
from fastapi import HTTPException, status
from redis import Redis
from pydantic import ValidationError
import json

from app.db.models import Hashtag, Post, User, post_mentions, post_hashtags
from app.db.redis import RedisManager
from app.posts.schemas.post_schemas import PostCreate, PostUpdate, PostResponse

logger = logging.getLogger(__name__)

class PostCache:
    """Handle post caching operations"""
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour

    async def get_post(self, post_id: int) -> Optional[Dict]:
        """Get post from cache"""
        cached = await self.redis.get(f"post:{post_id}")
        return json.loads(cached) if cached else None

    async def set_post(self, post_id: int, post_data: Dict):
        """Cache post data"""
        await self.redis.setex(
            f"post:{post_id}",
            self.cache_ttl,
            json.dumps(post_data)
        )

    async def invalidate_post(self, post_id: int):
        """Remove post from cache"""
        await self.redis.delete(f"post:{post_id}")

class PostValidator:
    """Validate post content and metadata"""
    def __init__(self, cache: PostCache):
        self.cache = cache
    
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
        window_key = f"post_rate:{user_id}:{int(datetime.utcnow().timestamp() // 3600)}"
        count = await self.cache.redis.get(window_key)
        
        if count and int(count) >= 100:  # 100 posts per hour limit
            raise ValidationError("Post rate limit exceeded")
            
        pipe = self.cache.redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, 3600)  # 1 hour window
        await pipe.execute()
        return True

    async def _contains_inappropriate_content(self, content: str) -> bool:
        """Check content against moderation rules"""
        # Implement content moderation logic
        return False

class EnhancedCorePostService:
    """Enhanced post service with caching and validation"""
    
    def __init__(self, cache: PostCache, validator: PostValidator):
        self.cache = cache
        self.validator = validator
        self.redis_manager = RedisManager()
        
    async def create_post(
        self, 
        session: AsyncSession, 
        user_id: int, 
        post_data: PostCreate
    ) -> PostResponse:
        """Create a new post with validation and caching"""
        # Validate user exists
        user = await self._get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate content
        await self.validator.validate_content(post_data.content)

        # Validate content and rate limit
        rate_limit_key = f"post_rate:{user_id}"
        if not await self.redis_manager.check_rate_limit(
            key=rate_limit_key,
            limit=100,  # 100 posts per hour
            window_seconds=3600
        ):
            raise HTTPException(
            status_code=429,
            detail="Post rate limit exceeded"
        )
            
         # Validate content and rate limit
        await self.validator.validate_content(post_data.content)
        await self.validator.validate_rate_limit(user_id)

        # Extract hashtags and mentions
        hashtags = await self._extract_entities(session, post_data.content, "hashtag")
        mentioned_user_ids = await self._extract_entities(session, post_data.content, "mention")


        # Create post instance
        post = Post(
            author_id=user_id,
            content=post_data.content,
            reply_to_id=post_data.reply_to_id
        )

        try:
            session.add(post)
            await session.commit()
            await session.refresh(post)
            
             # Store hashtags and mentions
            await self._batch_store_hashtags(session, post.id, hashtags)
            await self._batch_store_mentions(session, post.id, mentioned_user_ids)
            
            
            # Prepare response
            response = PostResponse(
                id=post.id,
                content=post.content,
                created_at=post.created_at,
                author_username=user.username,
                reply_to_id=post.reply_to_id
            )
            
            # Cache the new post
            await self.cache.set_post(post.id, response.dict())
            
            return response

        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create post"
            )


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
        stmt = (
            select(Post, User.username)
            .join(Post, User.id == Post.author_id)  # Join with User table
            .options(contains_eager(Post.author))  # Load author data eagerly
            .where(Post.id == post_id)
        )
        
        result = await session.execute(stmt)
        post: Optional[Post] = result.unique().scalar_one_or_none()
        
        row = result.first()
        if not row:
                return None
        
        post, username = row
            
        response = PostResponse(
            # Fields from PostBase
            content=post.content,
            reply_to_id=post.reply_to_id,
            
            # Fields from PostResponse
            id=post.id,
            created_at=post.created_at,
            author_username=username,
            like_count=post.like_count,  # Make sure these fields exist in Post model
            view_count=post.view_count,
            repost_count=post.repost_count
        )
        
        # Cache the post
        await self.redis_manager.set_post(post_id, response.dict())
        
        return response

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
            if post_data.content:
                # Clear existing hashtags and mentions
                await session.execute(
                    delete(post_hashtags).where(post_hashtags.c.post_id == post_id)
                )
                await session.execute(
                    delete(post_mentions).where(post_mentions.c.post_id == post_id)
                )
                
                # Extract and store new hashtags and mentions
                hashtags = await self._extract_entities(session, post_data.content, "hashtag")
                mentioned_user_ids = await self._extract_entities(session, post_data.content, "mention")
                
                await self._batch_store_hashtags(session, post_id, hashtags)
                await self._batch_store_mentions(session, post_id, mentioned_user_ids)

            # Update post content
            db_post.content = post_data.content or db_post.content
            db_post.updated_at = datetime.utcnow()
            
            await session.commit()
            await session.refresh(db_post)
            
            # Invalidate cache
            await self.cache.invalidate_post(post_id)
            
            # Return updated post
            return PostResponse(
                id=db_post.id,
                content=db_post.content,
                created_at=db_post.created_at,
                author_username=(await self._get_user(session, user_id)).username,
                reply_to_id=db_post.reply_to_id
            )

        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update post"
            )

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
            
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete post"
            )

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
            
            return {
                "items": [
                    PostResponse(
                        id=post.id,
                        content=post.content,
                        created_at=post.created_at,
                        author_username=post.author.username,
                        reply_to_id=post.reply_to_id
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
                    tag for tag in matches 
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
            hashtag = existing_hashtags.get(tag) or new_hashtags.pop(0)
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
            mentions: set[str]
        ) -> None:
            """Store mentions with batching"""
            if not mentions:
                return

            # Get or fetch mentioned users in batch
            existing_users = await session.execute(
                select(User).where(User.username.in_(mentions))
            )
            existing_users = {u.username: u for u in existing_users.scalars()}
            
            # Create mention associations
            for username in mentions:
                if user := existing_users.get(username):
                    await session.execute(
                        post_mentions.insert().values(
                            post_id=post_id,
                            user_id=user.id
                        )
                    )

            # Note: We silently skip mentions of non-existent users    

    async def _store_mentions(
        self,
        session: AsyncSession,
        post_id: int,
        user_ids: Set[int]
    ):
        """Store post mentions in association table"""
        if not user_ids:
            return

        # Create mention associations
        for user_id in user_ids:
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
            await self.cache.set_post(f"user:{user_id}", result.__dict__)
        return result