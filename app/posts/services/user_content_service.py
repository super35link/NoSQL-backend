from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import joinedload
from typing import Dict, List, Optional
from datetime import datetime
import logging

from app.db.models import User, Post, Thread, post_mentions, post_hashtags, Hashtag
from posts.schemas import PostResponse, ThreadResponse

logger = logging.getLogger(__name__)

class UserContentService:
    async def get_user_timeline(
        self,
        session: AsyncSession,
        username: str,
        content_type: str = "all",
        skip: int = 0,
        limit: int = 20
    ) -> Dict:
        """Get user's timeline with different content types"""
        # First get user
        user = await self._get_user_by_username(session, username)
        if not user:
            raise ValueError(f"User {username} not found")

        # Build base query
        query = select(Post).join(User)

        # Filter based on content type
        if content_type == "posts":
            query = query.where(
                and_(
                    Post.author_id == user.id,
                    Post.thread_id.is_(None),
                    Post.repost_id.is_(None)
                )
            )
        elif content_type == "threads":
            query = query.join(Thread).where(Thread.creator_id == user.id)
        elif content_type == "replies":
            query = query.where(
                and_(
                    Post.author_id == user.id,
                    Post.reply_to_id.isnot(None)
                )
            )
        elif content_type == "reposts":
            query = query.where(
                and_(
                    Post.author_id == user.id,
                    Post.repost_id.isnot(None)
                )
            )
        elif content_type == "mentions":
            query = (
                select(Post)
                .join(post_mentions)
                .where(post_mentions.c.user_id == user.id)
            )
        else:  # "all"
            query = query.where(Post.author_id == user.id)

        # Add joins for related data
        query = query.options(
            joinedload(Post.author),
            joinedload(Post.thread),
            joinedload(Post.hashtags)
        )

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
                await self._format_post_response(post) 
                for post in posts
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }

    async def get_user_activity_summary(
        self,
        session: AsyncSession,
        username: str
    ) -> Dict:
        """Get summary of user's content activity"""
        user = await self._get_user_by_username(session, username)
        if not user:
            raise ValueError(f"User {username} not found")

        # Get counts for different types of content
        post_count = await session.scalar(
            select(func.count())
            .select_from(Post)
            .where(
                and_(
                    Post.author_id == user.id,
                    Post.thread_id.is_(None),
                    Post.repost_id.is_(None)
                )
            )
        )

        thread_count = await session.scalar(
            select(func.count())
            .select_from(Thread)
            .where(Thread.creator_id == user.id)
        )

        reply_count = await session.scalar(
            select(func.count())
            .select_from(Post)
            .where(
                and_(
                    Post.author_id == user.id,
                    Post.reply_to_id.isnot(None)
                )
            )
        )

        repost_count = await session.scalar(
            select(func.count())
            .select_from(Post)
            .where(
                and_(
                    Post.author_id == user.id,
                    Post.repost_id.isnot(None)
                )
            )
        )

        mention_count = await session.scalar(
            select(func.count())
            .select_from(post_mentions)
            .where(post_mentions.c.user_id == user.id)
        )

        # Get most used hashtags
        hashtag_query = (
            select(Hashtag.tag, func.count(Hashtag.id).label('count'))
            .join(post_hashtags)
            .join(Post)
            .where(Post.author_id == user.id)
            .group_by(Hashtag.tag)
            .order_by(func.count(Hashtag.id).desc())
            .limit(5)
        )
        
        result = await session.execute(hashtag_query)
        top_hashtags = result.all()

        return {
            "username": username,
            "post_count": post_count,
            "thread_count": thread_count,
            "reply_count": reply_count,
            "repost_count": repost_count,
            "mention_count": mention_count,
            "top_hashtags": [
                {"tag": tag, "count": count}
                for tag, count in top_hashtags
            ],
            "total_content": post_count + thread_count + reply_count + repost_count
        }

    async def get_user_content_by_hashtag(
        self,
        session: AsyncSession,
        username: str,
        hashtag: str,
        skip: int = 0,
        limit: int = 20
    ) -> Dict:
        """Get user's content filtered by hashtag"""
        user = await self._get_user_by_username(session, username)
        if not user:
            raise ValueError(f"User {username} not found")

        query = (
            select(Post)
            .join(post_hashtags)
            .join(Hashtag)
            .where(
                and_(
                    Post.author_id == user.id,
                    Hashtag.tag == hashtag
                )
            )
            .options(
                joinedload(Post.author),
                joinedload(Post.thread),
                joinedload(Post.hashtags)
            )
        )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        result = await session.execute(
            query.order_by(Post.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        posts = result.unique().scalars().all()

        return {
            "hashtag": hashtag,
            "items": [
                await self._format_post_response(post)
                for post in posts
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }

    async def get_user_interactions(
        self,
        session: AsyncSession,
        username: str,
        interaction_type: str = "all",
        skip: int = 0,
        limit: int = 20
    ) -> Dict:
        """Get posts user has interacted with"""
        user = await self._get_user_by_username(session, username)
        if not user:
            raise ValueError(f"User {username} not found")

        # Build query based on interaction type
        if interaction_type == "likes":
            # This would need integration with engagement service
            pass
        elif interaction_type == "replies":
            query = (
                select(Post)
                .where(Post.reply_to_id.in_(
                    select(Post.id).where(Post.author_id == user.id)
                ))
                .options(
                    joinedload(Post.author),
                    joinedload(Post.thread),
                    joinedload(Post.hashtags)
                )
            )
        elif interaction_type == "mentions":
            query = (
                select(Post)
                .join(post_mentions)
                .where(post_mentions.c.user_id == user.id)
                .options(
                    joinedload(Post.author),
                    joinedload(Post.thread),
                    joinedload(Post.hashtags)
                )
            )
        else:  # all interactions
            query = (
                select(Post)
                .where(
                    or_(
                        Post.reply_to_id.in_(
                            select(Post.id).where(Post.author_id == user.id)
                        ),
                        Post.id.in_(
                            select(post_mentions.c.post_id)
                            .where(post_mentions.c.user_id == user.id)
                        )
                    )
                )
                .options(
                    joinedload(Post.author),
                    joinedload(Post.thread),
                    joinedload(Post.hashtags)
                )
            )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        result = await session.execute(
            query.order_by(Post.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        posts = result.unique().scalars().all()

        return {
            "interaction_type": interaction_type,
            "items": [
                await self._format_post_response(post)
                for post in posts
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }

    # Helper methods
    async def _get_user_by_username(
        self,
        session: AsyncSession,
        username: str
    ) -> Optional[User]:
        """Get user by username"""
        result = await session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def _format_post_response(self, post: Post) -> Dict:
        """Format post for response"""
        return {
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at,
            "author_username": post.author.username,
            "thread_id": post.thread_id,
            "reply_to_id": post.reply_to_id,
            "repost_id": post.repost_id,
            "hashtags": [tag.tag for tag in post.hashtags],
            "type": self._determine_post_type(post)
        }

    def _determine_post_type(self, post: Post) -> str:
        """Determine the type of post"""
        if post.thread_id:
            return "thread_post"
        elif post.reply_to_id:
            return "reply"
        elif post.repost_id:
            return "repost"
        return "post"