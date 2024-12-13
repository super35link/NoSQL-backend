from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from .models import Settings
from .schemas import SettingsUpdate

async def get_settings(db: AsyncSession, user_id: int) -> Settings:
    """Get user's settings or create if don't exist"""
    result = await db.execute(
        select(Settings).filter(Settings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = Settings(user_id=user_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return settings

async def update_settings(
    db: AsyncSession,
    user_id: int,
    data: SettingsUpdate
) -> Settings:
    """Update user settings"""
    settings = await get_settings(db, user_id)
    
    # Update only provided fields
    for key, value in data.dict(exclude_unset=True).items():
        setattr(settings, key, value)
    
    await db.commit()
    await db.refresh(settings)
    return settings

async def validate_settings(settings: Settings) -> bool:
    """Validate settings values"""
    valid_themes = ["light", "dark", "system"]
    valid_visibility = ["everyone", "followers", "nobody"]
    valid_reply_settings = ["everyone", "followers", "mentioned"]
    
    if settings.theme not in valid_themes:
        raise HTTPException(400, "Invalid theme setting")
    
    if settings.who_can_see_posts not in valid_visibility:
        raise HTTPException(400, "Invalid post visibility setting")
        
    if settings.who_can_reply not in valid_reply_settings:
        raise HTTPException(400, "Invalid reply setting")
    
    return True