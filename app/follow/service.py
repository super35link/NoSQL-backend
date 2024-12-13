from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models import User
from .models import Follow
from .schemas import FollowCreate, FollowUpdate

async def create_follow(db: AsyncSession, follower_id: int, data: FollowCreate) -> Follow:
    """Create a new follow relationship"""
    if follower_id == data.following_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    # Check if already following
    existing = await db.execute(
        select(Follow).where(
            (Follow.follower_id == follower_id) & 
            (Follow.following_id == data.following_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already following")

    follow = Follow(
        follower_id=follower_id,
        following_id=data.following_id,
        status="active"
    )
    db.add(follow)
    await db.commit()
    await db.refresh(follow)
    return follow

async def unfollow(db: AsyncSession, follower_id: int, following_id: int) -> None:
    """Remove a follow relationship"""
    result = await db.execute(
        select(Follow).where(
            (Follow.follower_id == follower_id) & 
            (Follow.following_id == following_id)
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        raise HTTPException(status_code=404, detail="Follow relationship not found")
    
    await db.delete(follow)
    await db.commit()

async def get_followers(db: AsyncSession, user_id: int) -> List[Follow]:
    """Get all followers for a user"""
    result = await db.execute(
        select(Follow).where(Follow.following_id == user_id)
    )
    return result.scalars().all()

async def get_following(db: AsyncSession, user_id: int) -> List[Follow]:
    """Get all users followed by a user"""
    result = await db.execute(
        select(Follow).where(Follow.follower_id == user_id)
    )
    return result.scalars().all()

async def get_follow_stats(db: AsyncSession, user_id: int) -> dict:
    """Get follow statistics for a user"""
    followers = await db.execute(
        select(func.count()).where(Follow.following_id == user_id)
    )
    following = await db.execute(
        select(func.count()).where(Follow.follower_id == user_id)
    )
    return {
        "followers_count": followers.scalar(),
        "following_count": following.scalar()
    }

async def update_follow_status(
    db: AsyncSession,
    follower_id: int,
    following_id: int,
    data: FollowUpdate
) -> Follow:
    """Update follow status (e.g., mute, block)"""
    result = await db.execute(
        select(Follow).where(
            (Follow.follower_id == follower_id) & 
            (Follow.following_id == following_id)
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        raise HTTPException(status_code=404, detail="Follow relationship not found")
    
    if data.status not in ["active", "muted", "blocked"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    follow.status = data.status
    await db.commit()
    await db.refresh(follow)
    return follow

async def validate_username(username: str) -> bool:
    if not username or not username.strip():
        return False
    if not username.isalnum() and '_' not in username:
        return False
    if len(username) > 50:
        return False
    return True

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Find a user by their username"""
    result = await db.execute(
        select(User).where(User.username == username)
    )
    return result.scalar_one_or_none()