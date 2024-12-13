from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import joinedload
from typing import Dict, Optional, List
from datetime import datetime
import logging
from fastapi import HTTPException, status

from app.db.models import Post, User
from .schemas import PostCreate, PostUpdate, PostResponse

logger = logging.getLogger(__name__)

class CorePostService:
    """Handles core post operations and management"""
    
    async def create_post(
        self, 
        session: AsyncSession, 
        user_id: int, 
        post_data: PostCreate
    ) -> PostResponse:
        """Create a new post"""
        # Validate user exists
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()

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
            
            return PostResponse(
                id=post.id,
                content=post.content,
                created_at=post.created_at,
                author_username=user.username,
                reply_to_id=post.reply_to_id
            )

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
        """Get a single post by ID"""
        result = await session.execute(
            select(Post)
            .options(joinedload(Post.author))
            .where(Post.id == post_id)
        )
        post = result.unique().scalar_one_or_none()
        
        if not post:
            return None
            
        return PostResponse(
            id=post.id,
            content=post.content,
            created_at=post.created_at,
            author_username=post.author.username,
            reply_to_id=post.reply_to_id
        )

    async def update_post(
        self, 
        session: AsyncSession, 
        user_id: int, 
        post_id: int, 
        post_data: PostUpdate
    ) -> PostResponse:
        """Update an existing post"""
        # Get existing post
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
        
        # Update post
        update_data = post_data.dict(exclude_unset=True)
        try:
            await session.execute(
                update(Post)
                .where(Post.id == post_id)
                .values(**update_data, updated_at=datetime.utcnow())
            )
            await session.commit()
            
            return await self.get_post(session, post_id)

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
        """Delete a post"""
        # Verify post exists and ownership
        result = await session.execute(
            select(Post).where(Post.id == post_id)
        )
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.author_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this post")
        
        try:
            await session.execute(delete(Post).where(Post.id == post_id))
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete post"
            )

    async def get_posts_paginated(
        self,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None
    ) -> Dict:
        """Get paginated posts with optional user filter"""
        query = select(Post).options(joinedload(Post.author))
        
        if user_id:
            query = query.where(Post.author_id == user_id)
        
        try:
            # Get total count
            total = await session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            
            # Get paginated results
            result = await session.execute(
                query.order_by(Post.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            
            posts = result.unique().scalars().all()
            
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
                "total": total,
                "skip": skip,
                "limit": limit
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
        """Get total number of posts for a user"""
        result = await session.scalar(
            select(func.count()).select_from(
                select(Post).where(Post.author_id == user_id).subquery()
            )
        )
        return result

    async def validate_post_ownership(
        self, 
        session: AsyncSession, 
        post_id: int, 
        user_id: int
    ) -> bool:
        """Validate if a user owns a post"""
        result = await session.scalar(
            select(Post)
            .where(Post.id == post_id)
            .where(Post.author_id == user_id)
        )
        return bool(result)