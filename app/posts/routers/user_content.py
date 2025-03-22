from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.auth.users import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from app.posts.services.user_content_service import UserContentService

router = APIRouter(prefix="/users", tags=["user-content"])
user_content_service = UserContentService()

@router.get("/{username}/timeline")
async def get_user_timeline(
    username: str,
    content_type: str = Query(
        default="all",
        enum=["all", "posts", "threads", "replies", "reposts", "mentions"]
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get user's timeline with different content types"""
    return await user_content_service.get_user_timeline(
        session=session,
        username=username,
        content_type=content_type,
        skip=skip,
        limit=limit
    )

@router.get("/{username}/activity")
async def get_user_activity(
    username: str,
    session: AsyncSession = Depends(get_async_session)
):
    """Get summary of user's content activity"""
    return await user_content_service.get_user_activity_summary(
        session=session,
        username=username
    )

@router.get("/{username}/hashtags/{hashtag}")
async def get_user_content_by_hashtag(
    username: str,
    hashtag: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get user's content filtered by hashtag"""
    return await user_content_service.get_user_content_by_hashtag(
        session=session,
        username=username,
        hashtag=hashtag,
        skip=skip,
        limit=limit
    )

@router.get("/{username}/interactions")
async def get_user_interactions(
    username: str,
    interaction_type: str = Query(
        default="all",
        enum=["all", "likes", "replies", "mentions"]
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get posts user has interacted with"""
    return await user_content_service.get_user_interactions(
        session=session,
        username=username,
        interaction_type=interaction_type,
        skip=skip,
        limit=limit
    )

# Current user specific endpoints
@router.get("/me/timeline")
async def get_own_timeline(
    content_type: str = Query(
        default="all",
        enum=["all", "posts", "threads", "replies", "reposts", "mentions"]
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get current user's timeline"""
    return await user_content_service.get_user_timeline(
        session=session,
        username=user.username,
        content_type=content_type,
        skip=skip,
        limit=limit
    )

@router.get("/me/activity")
async def get_own_activity(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get current user's activity summary"""
    return await user_content_service.get_user_activity_summary(
        session=session,
        username=user.username
    )