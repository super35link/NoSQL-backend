from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from .models import Profile, ProfileView, ProfileMedia, blocked_users
from .schemas import ProfileUpdate, ProfilePrivacyUpdate, MediaUpload

async def get_profile(db: AsyncSession, user_id: int) -> Profile:
    """Get user's own profile or create if doesn't exist"""
    result = await db.execute(select(Profile).filter(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        profile = Profile(user_id=user_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    
    return profile

async def get_user_profile(db: AsyncSession, target_user_id: int, current_user_id: int) -> Profile:
    """Get another user's profile with privacy check"""
    profile = await db.execute(
        select(Profile).filter(Profile.user_id == target_user_id)
    )
    profile = profile.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Check if user is blocked
    is_blocked = await db.execute(
        select(blocked_users).where(
            (blocked_users.c.blocker_id == profile.id) &
            (blocked_users.c.blocked_id == current_user_id)
        )
    )
    if is_blocked.first():
        raise HTTPException(status_code=403, detail="Access denied")

    # Record profile view if not own profile
    if current_user_id != target_user_id:
        profile_view = ProfileView(
            profile_id=profile.id,
            viewer_id=current_user_id
        )
        db.add(profile_view)
        profile.profile_views += 1
        await db.commit()

    return profile

async def update_profile(db: AsyncSession, user_id: int, data: ProfileUpdate) -> Profile:
    """Update user's profile information"""
    profile = await get_profile(db, user_id)
    
    for key, value in data.dict(exclude_unset=True).items():
        setattr(profile, key, value)
    
    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return profile

async def update_privacy(db: AsyncSession, user_id: int, data: ProfilePrivacyUpdate) -> Profile:
    """Update privacy settings"""
    profile = await get_profile(db, user_id)
    
    profile.is_private = data.is_private
    profile.show_activity_status = data.show_activity_status
    await db.commit()
    await db.refresh(profile)
    return profile

async def block_user(db: AsyncSession, user_id: int, blocked_user_id: int) -> None:
    """Block a user"""
    if user_id == blocked_user_id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")
    
    profile = await get_profile(db, user_id)
    blocked_profile = await get_profile(db, blocked_user_id)
    
    stmt = blocked_users.insert().values(
        blocker_id=profile.id,
        blocked_id=blocked_profile.id
    )
    await db.execute(stmt)
    await db.commit()

async def get_blocked_users(db: AsyncSession, user_id: int) -> List[int]:
    """Get list of blocked user IDs"""
    profile = await get_profile(db, user_id)
    result = await db.execute(
        select(blocked_users.c.blocked_id).where(
            blocked_users.c.blocker_id == profile.id
        )
    )
    return [row[0] for row in result]

async def get_profile_stats(db: AsyncSession, user_id: int) -> dict:
    """Get profile statistics"""
    profile = await get_profile(db, user_id)
    
    # Get views in last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    daily_views = await db.execute(
        select(func.count(ProfileView.id)).where(
            (ProfileView.profile_id == profile.id) &
            (ProfileView.viewed_at >= yesterday)
        )
    )
    daily_views = daily_views.scalar()

    # Get most active times
    active_times = await db.execute(
        select(func.date_trunc('hour', ProfileView.viewed_at).label('hour'))
        .where(ProfileView.profile_id == profile.id)
        .group_by('hour')
        .order_by(func.count().desc())
        .limit(5)
    )
    
    return {
        "total_views": profile.profile_views,
        "total_posts": profile.posts_count,
        "total_saved": profile.saved_posts_count,
        "total_media": profile.media_count,
        "avg_daily_views": daily_views,
        "most_active_times": [time[0].strftime("%H:%M") for time in active_times]
    }

async def upload_media(
    db: AsyncSession, 
    user_id: int, 
    file_url: str, 
    media_type: str
) -> Profile:
    """Upload profile media (avatar or banner)"""
    if media_type not in ['avatar', 'banner']:
        raise HTTPException(status_code=400, detail="Invalid media type")
    
    profile = await get_profile(db, user_id)
    
    # Deactivate old media
    old_media = await db.execute(
        select(ProfileMedia).where(
            (ProfileMedia.profile_id == profile.id) &
            (ProfileMedia.media_type == media_type) &
            (ProfileMedia.is_active == True)
        )
    )
    if old_media := old_media.scalar_one_or_none():
        old_media.is_active = False
    
    # Create new media
    new_media = ProfileMedia(
        profile_id=profile.id,
        media_type=media_type,
        media_url=file_url
    )
    db.add(new_media)
    
    # Update profile
    setattr(profile, f"{media_type}_url", file_url)
    await db.commit()
    await db.refresh(profile)
    
    return profile

async def get_collections(db: AsyncSession, user_id: int) -> dict:
    """Get user's collections (posts, saved posts, media)"""
    profile = await get_profile(db, user_id)
    
    # Here you would typically join with posts and media tables
    # For now, returning dummy data
    return {
        "posts": [],  # Will be populated from posts table
        "saved_posts": [],  # Will be populated from saved_posts table
        "media": []  # Will be populated from profile_media table
    }