from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Path, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.users import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from app.posts.services.engagement_service import PostEngagementService
from app.posts.schemas.engagement_schemas import EngagementStats, UserEngagement

router = APIRouter(prefix="/engagement", tags=["engagement"])

@router.post(
    "/{post_id}/like",
    response_model=dict,
    status_code=200,
    responses={
        404: {"description": "Post not found"},
        409: {"description": "Already liked"}
    }
)
async def like_post(
    post_id: int = Path(..., description="The ID of the post to like"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Toggle like status for a post"""
    engagement_service = PostEngagementService(session)
    liked = await engagement_service.toggle_like(post_id, user.id)
    return {"liked": liked}

@router.get(
    "/{post_id}/stats",
    response_model=EngagementStats,
    responses={404: {"description": "Post not found"}}
)
async def get_post_engagement(
    post_id: int = Path(..., description="The ID of the post to get stats for"),
    session: AsyncSession = Depends(get_async_session)
):
    engagement_service = PostEngagementService(session)
    return await engagement_service.get_engagement_stats(post_id)

@router.get(
    "/{post_id}/user/{user_id}",
    response_model=UserEngagement,
    responses={404: {"description": "Post or user not found"}}
)
async def get_user_engagement(
    post_id: int = Path(..., description="The ID of the post"),
    user_id: int = Path(..., description="The ID of the user"),
    session: AsyncSession = Depends(get_async_session)
):
    engagement_service = PostEngagementService(session)
    return await engagement_service.get_user_engagement(user_id, post_id)

@router.post("/{post_id}/view")
async def record_view(
    post_id: int = Path(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    engagement_service = PostEngagementService(session)
    await engagement_service.increment_views(post_id, user.id)
    return {"success": True}

# In engagement.py
@router.get("/trending", response_model=List[Dict])
async def get_trending_posts(
    limit: int = 10,
    hours: int = 24,
    post_id: Optional[int] = None,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    engagement_service = PostEngagementService(db)
    return await engagement_service.get_trending_posts(
        limit=limit,
        hours=hours,
        user_id=current_user.id
    )