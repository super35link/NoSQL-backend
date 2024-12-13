from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import joinedload
from typing import Dict, List, Optional
from datetime import datetime
import logging
from fastapi import HTTPException, status

from app.db.models import Thread, Post, User, ThreadStatus
from .schemas import ThreadCreate, PostCreate, ThreadResponse, PostResponse

logger = logging.getLogger(__name__)

class ThreadService:
    async def start_thread(
        self,
        session: AsyncSession,
        user_id: int,
        initial_post: PostCreate
    ) -> Dict:
        """Start a new thread with first post"""
        # Create thread
        thread = Thread(
            creator_id=user_id,
            created_at=datetime.utcnow(),
            status=ThreadStatus.ACTIVE

        )
        session.add(thread)
        await session.flush()  # Get thread ID

        # Create first post
        first_post = Post(
            author_id=user_id,
            content=initial_post.content,
            thread_id=thread.id,
            position_in_thread=1
        )
        session.add(first_post)
        
        try:
            await session.commit()
            await session.refresh(thread)
            await session.refresh(first_post)
            
            return {
                "thread_id": thread.id,
                "status": thread.status.value,
                "first_post": PostResponse(
                    id=first_post.id,
                    content=first_post.content,
                    created_at=first_post.created_at,
                    author_username=(await self._get_username(session, user_id)),
                    thread_id=thread.id,
                    position_in_thread=1
                )
            }
        except Exception as e:
            await session.rollback()
            logger.error(f"Error starting thread: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create thread"
            )

    async def add_to_thread(
        self,
        session: AsyncSession,
        user_id: int,
        thread_id: int,
        post_content: str
    ) -> PostResponse:
        """Add new post to existing thread"""
        thread = await self._get_thread_with_creator(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        if thread.creator_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Only thread creator can add to thread"
            )

        if thread.status == ThreadStatus.COMPLETE:
            raise HTTPException(
                status_code=400,
                detail="Cannot add to completed thread"
            )

        next_position = await self._get_next_position(session, thread_id)
        new_post = Post(
            author_id=user_id,
            content=post_content,
            thread_id=thread_id,
            position_in_thread=next_position
        )
        session.add(new_post)

        try:
            await session.commit()
            await session.refresh(new_post)
            
            return PostResponse(
                id=new_post.id,
                content=new_post.content,
                created_at=new_post.created_at,
                author_username=(await self._get_username(session, user_id)),
                thread_id=thread_id,
                position_in_thread=next_position
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Error adding to thread: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add to thread"
            )
            
    async def complete_thread(
        self,
        session: AsyncSession,
        user_id: int,
        thread_id: int
    ) -> Dict:
        """Mark thread as complete"""
        thread = await self._get_thread_with_creator(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        if thread.creator_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Only thread creator can complete thread"
            )
            
        if thread.status == ThreadStatus.COMPLETE:
            raise HTTPException(
                status_code=400,
                detail="Thread is already completed"
            )

        try:
            thread.status = ThreadStatus.COMPLETE
            thread.completed_at = datetime.utcnow()
            await session.commit()
            
            return {
                "thread_id": thread_id,
                "status": ThreadStatus.COMPLETE.value,
                "completed_at": thread.completed_at
            }
        except Exception as e:
            await session.rollback()
            logger.error(f"Error completing thread: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete thread"
            )

    async def reactivate_thread(
        self,
        session: AsyncSession,
        user_id: int,
        thread_id: int
    ) -> Dict:
        """Reactivate a completed thread"""
        thread = await self._get_thread_with_creator(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        if thread.creator_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Only thread creator can reactivate thread"
            )
            
        if thread.status == ThreadStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Thread is already active"
            )

        try:
            thread.status = ThreadStatus.ACTIVE
            thread.completed_at = None
            await session.commit()
            
            return {
                "thread_id": thread_id,
                "status": ThreadStatus.ACTIVE.value,
                "reactivated_at": datetime.utcnow()
            }
        except Exception as e:
            await session.rollback()
            logger.error(f"Error reactivating thread: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reactivate thread"
            )
    async def get_thread_posts(
        self,
        session: AsyncSession,
        thread_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> Dict:
        """Get all posts in a thread, ordered by position"""
        # Verify thread exists
        thread = await self._get_thread_with_creator(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Get posts with author info
        query = (
            select(Post)
            .options(joinedload(Post.author))
            .where(Post.thread_id == thread_id)
            .order_by(Post.position_in_thread)
        )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        result = await session.execute(
            query.offset(skip).limit(limit)
        )
        
        posts = result.unique().scalars().all()

        return {
            "thread_id": thread_id,
            "creator_username": thread.author.username,
            "created_at": thread.created_at,
            "posts": [
                PostResponse(
                    id=post.id,
                    content=post.content,
                    created_at=post.created_at,
                    author_username=post.author.username,
                    thread_id=thread_id,
                    position_in_thread=post.position_in_thread
                ) for post in posts
            ],
            "total_posts": total,
            "skip": skip,
            "limit": limit
        }

    async def delete_from_thread(
        self,
        session: AsyncSession,
        user_id: int,
        thread_id: int,
        post_id: int
    ) -> bool:
        """Delete a specific post from thread"""
        # Verify thread and post exist
        thread = await self._get_thread_with_creator(session, thread_id)
        if not thread or thread.creator_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to modify this thread"
            )

        post = await session.get(Post, post_id)
        if not post or post.thread_id != thread_id:
            raise HTTPException(status_code=404, detail="Post not found in thread")

        try:
            # Delete the post
            await session.execute(
                delete(Post).where(Post.id == post_id)
            )
            
            # Reorder remaining posts if needed
            await self._reorder_thread_positions(session, thread_id)
            
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting from thread: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete from thread"
            )

    async def get_user_threads(
        self,
        session: AsyncSession,
        user_id: int,
        status: Optional[ThreadStatus] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Dict:
        """Get user's threads with optional status filter"""
        query = (
            select(Thread)
            .options(joinedload(Thread.author))
            .where(Thread.creator_id == user_id)
        )

        if status:
            query = query.where(Thread.status == status)

        query = query.order_by(Thread.created_at.desc())

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        result = await session.execute(
            query.offset(skip).limit(limit)
        )
        
        threads = result.unique().scalars().all()

        return {
            "items": [
                {
                    "thread_id": thread.id,
                    "status": thread.status.value,
                    "created_at": thread.created_at,
                    "completed_at": thread.completed_at,
                    "creator_username": thread.author.username,
                    "first_post": await self._get_first_post(session, thread.id)
                }
                for thread in threads
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }

    # Helper methods
    async def _get_thread_with_creator(
        self,
        session: AsyncSession,
        thread_id: int
    ) -> Optional[Thread]:
        """Get thread with creator info"""
        result = await session.execute(
            select(Thread)
            .options(joinedload(Thread.author))
            .where(Thread.id == thread_id)
        )
        return result.unique().scalar_one_or_none()

    async def _get_next_position(
        self,
        session: AsyncSession,
        thread_id: int
    ) -> int:
        """Get next available position in thread"""
        result = await session.scalar(
            select(func.max(Post.position_in_thread))
            .where(Post.thread_id == thread_id)
        )
        return (result or 0) + 1

    async def _get_username(
        self,
        session: AsyncSession,
        user_id: int
    ) -> str:
        """Get username for user_id"""
        result = await session.get(User, user_id)
        return result.username if result else "Unknown"

    async def _get_first_post(
        self,
        session: AsyncSession,
        thread_id: int
    ) -> Optional[Dict]:
        """Get first post of a thread"""
        result = await session.execute(
            select(Post)
            .options(joinedload(Post.author))
            .where(Post.thread_id == thread_id)
            .where(Post.position_in_thread == 1)
        )
        post = result.unique().scalar_one_or_none()
        if post:
            return {
                "id": post.id,
                "content": post.content,
                "created_at": post.created_at,
                "author_username": post.author.username
            }
        return None

    async def _reorder_thread_positions(
        self,
        session: AsyncSession,
        thread_id: int
    ):
        """Reorder positions after deletion"""
        posts = await session.execute(
            select(Post)
            .where(Post.thread_id == thread_id)
            .order_by(Post.created_at)
        )
        for i, post in enumerate(posts.scalars(), 1):
            post.position_in_thread = i
            