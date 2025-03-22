# app/posts/router/hashtag.py
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional

from app.auth.users import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from app.posts.services.hashtag_service import HashtagService

router = APIRouter(prefix="/hashtags", tags=["hashtags"])
service = HashtagService()

@router.get("/trending")
async def get_trending_hashtags(
    timeframe: str = Query(default="24h", enum=["1h", "24h", "7d", "30d"]),
    category: Optional[str] = None,
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0)
):
    """Get trending hashtags with optional filters"""
    return await service.get_trending_hashtags(
        timeframe=timeframe,
        category=category,
        limit=limit,
        offset=offset
    )

@router.get("/categories")
async def get_hashtag_categories():
    """Get available hashtag categories"""
    return await service.get_hashtag_categories()

@router.post("/{hashtag}/follow")
async def follow_hashtag(
    hashtag: str = Path(..., description="Hashtag to follow"),
    user: User = Depends(current_active_user)
):
    """Follow a hashtag"""
    result = await service.follow_hashtag(user.id, hashtag)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to follow hashtag")
        )
    return result

@router.post("/{hashtag}/unfollow")
async def unfollow_hashtag(
    hashtag: str = Path(..., description="Hashtag to unfollow"),
    user: User = Depends(current_active_user)
):
    """Unfollow a hashtag"""
    result = await service.unfollow_hashtag(user.id, hashtag)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to unfollow hashtag")
        )
    return result

@router.get("/followed")
async def get_followed_hashtags(
    limit: int = Query(default=100, le=500),
    user: User = Depends(current_active_user)
):
    """Get hashtags followed by current user"""
    return await service.get_followed_hashtags(user.id, limit)

@router.post("/check-follows")
async def check_follows_hashtags(
    hashtags_data: Dict[str, List[str]],  # Request body to validate
    user: User = Depends(current_active_user)
):
    """Check if user follows multiple hashtags"""
    # Extract hashtags from the request body
    hashtags = hashtags_data.get("hashtags", [])
    
    # Validate that hashtags is a list of strings
    if not isinstance(hashtags, list) or not all(isinstance(tag, str) for tag in hashtags):
        raise HTTPException(
            status_code=422,
            detail="Invalid hashtags format. Expected a list of strings."
        )
    
    return await service.check_follows_hashtags(user.id, hashtags)

@router.get("/{hashtag}/posts")
async def get_posts_by_hashtag(
    hashtag: str = Path(..., description="The hashtag to find posts for"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user)
):
    """Get posts associated with a specific hashtag"""
    return await service.get_posts_by_hashtag(
        session=session,
        hashtag=hashtag,
        skip=skip,
        limit=limit
    )

@router.get("/{hashtag}/related")
async def get_related_hashtags(
    hashtag: str = Path(..., description="Source hashtag"),
    limit: int = Query(default=10, le=30)
):
    """Get semantically related hashtags"""
    return await service.find_related_hashtags(hashtag, limit)

@router.post("/suggest")
async def suggest_hashtags(
    content: str,
    limit: int = Query(default=5, le=20)
):
    """Suggest hashtags for content based on its semantic meaning"""
    return await service.suggest_hashtags(content, limit)

@router.post("/{hashtag}/view")
async def record_hashtag_view(
    hashtag: str = Path(..., description="Hashtag being viewed"),
    user: User = Depends(current_active_user)
):
    """Record a view for a hashtag (increases trending score)"""
    await service._record_hashtag_view(hashtag, user.id)
    return {"success": True}