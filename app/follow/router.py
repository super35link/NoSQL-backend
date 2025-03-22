from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.users import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from . import service
from .schemas import FollowList, FollowRead, FollowCreate, FollowUpdate, FollowStats

router = APIRouter(prefix="/follow", tags=["follow"])

@router.post("/{username}")
async def follow_user(
    username: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Follow a user by their username"""
    # First find the user by username
    target_user = await service.get_user_by_username(db, username)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return await service.create_follow(db, user.id, FollowCreate(following_id=target_user.id))

@router.delete("/unfollow/{username}")
async def unfollow_user(
    username: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Unfollow a user by username"""
    await service.unfollow(db, user.username, username)
    return {"message": f"Successfully unfollowed @{username}"}

@router.get("/followers", response_model=FollowList)
async def get_my_followers(
    page: int = 1,
    limit: int = 20,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get current user's followers with pagination"""
    return await service.get_followers(db, user.username, page, limit)

@router.get("/following", response_model=FollowList)
async def get_my_following(
    page: int = 1,
    limit: int = 20,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get users that current user is following with pagination"""
    return await service.get_following(db, user.username, page, limit)

@router.get("/stats", response_model=FollowStats)
async def get_my_follow_stats(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get follow statistics for current user"""
    return await service.get_follow_stats(db, user.username)

@router.put("/{username}/status", response_model=FollowRead)
async def update_follow_status(
    username: str,
    data: FollowUpdate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Update follow status (mute/block) for a user"""
    return await service.update_follow_status(
        db, 
        user.username, 
        username, 
        data
    )

@router.get("/{username}/stats", response_model=FollowStats)
async def get_user_follow_stats(
    username: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Get follow statistics for any user by username"""
    return await service.get_follow_stats(db, username)


