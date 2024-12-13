from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import joinedload, selectinload
from typing import Dict, Optional
from datetime import datetime
import logging
from fastapi import HTTPException, status

from .schemas import PostCreate, PostUpdate, ThreadCreate, ThreadUpdate, PostResponse, ThreadResponse
from .embedding_service import PostEmbeddingService
from .engagement_service import PostEngagementService
from app.db.models import User, post_mentions, post_hashtags, Post, Thread, Hashtag

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PostService:
    def __init__(self):
        self.embedding_service = PostEmbeddingService()
        self.engagement_service = PostEngagementService()

    async def create_post(self, session: AsyncSession, user_id: int, post_data: PostCreate) -> PostResponse:
        # First get user
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()

        post = Post(
            author_id=user_id,
            content=post_data.content,
            thread_id=post_data.thread_id,
            reply_to_id=post_data.reply_to_id
        )

        session.add(post)
        await session.commit()
        await session.refresh(post)

        try:
            # Process embedding using embedding service
            await self.embedding_service.process_post(
                post_id=post.id,
                content=post_data.content,
                metadata={
                    "author_id": user_id,
                    "created_at": post.created_at
                }
            )
            
            # Initialize engagement tracking
            await self.engagement_service.initialize_post(post.id)

        except Exception as e:
            logger.error(f"Error processing post {post.id}: {e}")
            # Post is still created even if embedding/engagement fails

        return PostResponse(
            id=post.id,
            content=post.content,
            created_at=post.created_at,
            author_username=user.username,
            thread_id=post.thread_id,
            reply_to_id=post.reply_to_id,
            position_in_thread=post.position_in_thread,
            like_count=0,  # Initial engagement metrics
            view_count=0,
            repost_count=post.repost_count
        )

    async def get_post(self, session: AsyncSession, post_id: int) -> Optional[PostResponse]:
        result = await session.execute(
            select(Post)
            .options(joinedload(Post.author))
            .where(Post.id == post_id)
        )
        post = result.unique().scalar_one_or_none()
        
        if not post:
            return None

        # Get engagement stats
        engagement_stats = await self.engagement_service.get_engagement_stats(post_id)
            
        return PostResponse(
            id=post.id,
            content=post.content,
            created_at=post.created_at,
            author_username=post.author.username,
            thread_id=post.thread_id,
            reply_to_id=post.reply_to_id,
            position_in_thread=post.position_in_thread,
            like_count=engagement_stats.get("likes", 0),
            view_count=engagement_stats.get("views", 0),
            repost_count=post.repost_count
        )

    async def update_post(self, session: AsyncSession, user_id: int, post_id: int, post_data: PostUpdate) -> Post:
        post = await self.get_post(session, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.author_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this post")
        
        update_data = post_data.dict(exclude_unset=True)
        await session.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(**update_data)
        )
        await session.commit()

        # Update embedding if content changed
        if "content" in update_data:
            await self.embedding_service.process_post(
                post_id=post_id,
                content=update_data["content"],
                metadata={
                    "author_id": user_id,
                    "updated_at": datetime.utcnow()
                }
            )

        return await self.get_post(session, post_id)

    async def delete_post(self, session: AsyncSession, user_id: int, post_id: int) -> bool:
        post = await self.get_post(session, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.author_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this post")
        
        # Delete from all services
        try:
            await self.embedding_service.delete_post_embedding(post_id)
            await self.engagement_service.delete_post_engagement(post_id)
            await session.execute(delete(Post).where(Post.id == post_id))
            await session.commit()
        except Exception as e:
            logger.error(f"Error deleting post {post_id}: {e}")
            raise

        return True

    async def get_posts_paginated(
        self,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
        thread_id: Optional[int] = None
    ) -> Dict:
        query = select(Post).options(joinedload(Post.author))
        
        if user_id:
            query = query.where(Post.author_id == user_id)
        if thread_id:
            query = query.where(Post.thread_id == thread_id)
        
        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )
        
        result = await session.execute(
            query.order_by(Post.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        posts = result.unique().scalars().all()
        
        # Get engagement stats for all posts
        post_responses = []
        for post in posts:
            engagement_stats = await self.engagement_service.get_engagement_stats(post.id)
            post_responses.append(PostResponse(
                id=post.id,
                content=post.content,
                created_at=post.created_at,
                author_username=post.author.username,
                thread_id=post.thread_id,
                reply_to_id=post.reply_to_id,
                position_in_thread=post.position_in_thread,
                like_count=engagement_stats.get("likes", 0),
                view_count=engagement_stats.get("views", 0),
                repost_count=post.repost_count
            ))

        return {
            "items": post_responses,
            "total": total,
            "skip": skip,
            "limit": limit
        }

    async def create_repost(
        self,
        session: AsyncSession,
        user_id: int,
        original_post_id: int,
        content: Optional[str] = None
    ) -> Post:
        original_post = await self.get_post(session, original_post_id)
        if not original_post:
            raise HTTPException(status_code=404, detail="Original post not found")
        
        repost_content = content if content is not None else original_post.content
        repost = Post(
            author_id=user_id,
            content=repost_content,
            repost_id=original_post_id
        )
        
        session.add(repost)
        await session.commit()
        await session.refresh(repost)

        # Initialize engagement for repost
        await self.engagement_service.initialize_post(repost.id)

        return repost

    # Thread-related functions remain unchanged
    async def create_thread(self, session: AsyncSession, user_id: int, thread_data: ThreadCreate) -> Thread:
        thread = Thread(creator_id=user_id, is_collaborative=thread_data.is_collaborative)
        session.add(thread)
        await session.flush()

        # Create posts in thread
        for idx, content in enumerate(thread_data.posts, 1):
            post = Post(
                author_id=user_id,
                content=content,
                thread_id=thread.id,
                position_in_thread=idx
            )
            session.add(post)
            # Initialize engagement for each post
            await self.engagement_service.initialize_post(post.id)

        await session.commit()
        await session.refresh(thread)
        return thread

    async def get_thread(self, session: AsyncSession, thread_id: int) -> Optional[Thread]:
        result = await session.execute(
            select(Thread).where(Thread.id == thread_id)
        )
        return result.scalar_one_or_none()

    async def update_thread(
        self,
        session: AsyncSession,
        user_id: int,
        thread_id: int,
        thread_data: ThreadUpdate
    ) -> Thread:
        thread = await self.get_thread(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        if thread.creator_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this thread")
        
        update_data = thread_data.dict(exclude_unset=True)
        await session.execute(
            update(Thread)
            .where(Thread.id == thread_id)
            .values(**update_data)
        )
        await session.commit()
        await session.refresh(thread)
        return thread

    async def delete_thread(self, session: AsyncSession, user_id: int, thread_id: int) -> bool:
        thread = await self.get_thread(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        if thread.creator_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this thread")
        
        # Get all posts in thread
        result = await session.execute(
            select(Post).where(Post.thread_id == thread_id)
        )
        posts = result.scalars().all()

        # Delete engagement and embeddings for all posts
        for post in posts:
            await self.embedding_service.delete_post_embedding(post.id)
            await self.engagement_service.delete_post_engagement(post.id)

        # Delete all posts and thread
        await session.execute(delete(Post).where(Post.thread_id == thread_id))
        await session.execute(delete(Thread).where(Thread.id == thread_id))
        await session.commit()
        return True

    async def get_thread_with_posts(
        self,
        session: AsyncSession,
        thread_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> Dict:
        thread = await self.get_thread(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        posts = await self.get_posts_paginated(
            session,
            skip=skip,
            limit=limit,
            thread_id=thread_id
        )
        
        return {
            "thread": ThreadResponse.from_orm(thread),
            "posts": posts
        }

    # Engagement-specific functions
    async def toggle_like(self, session: AsyncSession, user_id: int, post_id: int) -> Dict:
        post = await self.get_post(session, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        liked = await self.engagement_service.toggle_like(post_id, user_id)
        
        # Update Qdrant with new engagement metrics
        engagement_stats = await self.engagement_service.get_engagement_stats(post_id)
        await self.embedding_service.update_post_metadata(
            post_id,
            {
                "engagement": {
                    "likes": engagement_stats["likes"],
                    "views": engagement_stats["views"],
                    "last_updated": datetime.utcnow().isoformat()
                }
            }
        )

        return {
            "success": True,
            "liked": liked,
            "like_count": engagement_stats["likes"]
        }

    async def record_view(self, session: AsyncSession, user_id: int, post_id: int):
        post = await self.get_post(session, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        await self.engagement_service.increment_views(post_id, user_id)
        
        # Update Qdrant
        engagement_stats = await self.engagement_service.get_engagement_stats(post_id)
        await self.embedding_service.update_post_metadata(
            post_id,
            {
                "engagement": {
                    "views": engagement_stats["views"],
                    "unique_viewers": engagement_stats["unique_viewers"],
                    "last_updated": datetime.utcnow().isoformat()
                }
            }
        )

    async def search_similar_posts(
        self,
        query: str,
        limit: int = 10,
        min_likes: int = 0,
        min_views: int = 0
    ) -> Dict:
        try:
            embedding = await self.embedding_service.generate_embedding(query)
            
            # Search with engagement filters
            filter_conditions = []
            if min_likes > 0:
                filter_conditions.append({
                    "range": {
                        "engagement.likes": {"gte": min_likes}
                    }
                })
            if min_views > 0:
                filter_conditions.append({
                    "range": {
                        "engagement.views": {"gte": min_views}
                    }
                })

            similar_posts = await self.embedding_service.search_similar_posts(
                query_vector=embedding,
                limit=limit,
                query_filter={"must": filter_conditions} if filter_conditions else None
            )
            
            return similar_posts
            
        except Exception as e:
            logger.error(f"Error searching similar posts: {e}")
            raise

    # Keep all other existing methods...
    async def get_posts_by_username(self, session: AsyncSession, username: str,
                                  content_type: str = "posts", skip: int = 0, limit: int = 20) -> Dict:
        # Your existing implementation...
        pass

    async def get_posts_by_hashtag(self, session: AsyncSession, hashtag: str,
                                 skip: int = 0, limit: int = 20) -> Dict:
        # Your existing implementation...
        pass