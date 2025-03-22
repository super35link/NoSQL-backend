from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.users import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from . import service
from .schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("", response_model=SettingsRead)
async def get_my_settings(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get current user's settings"""
    return await service.get_settings(db, user.id)

@router.put("", response_model=SettingsRead)
async def update_my_settings(
    data: SettingsUpdate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Update current user's settings"""
    settings = await service.update_settings(db, user.id, data)
    await service.validate_settings(settings)
    return settings

@router.get("/theme", response_model=str)
async def get_theme(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get user's theme preference"""
    settings = await service.get_settings(db, user.id)
    return settings.theme

@router.get("/language", response_model=str)
async def get_language(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get user's language preference"""
    settings = await service.get_settings(db, user.id)
    return settings.language

@router.put("/muted-words", response_model=list[str])
async def update_muted_words(
    words: list[str],
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Update user's muted words list"""
    settings = await service.update_settings(
        db, 
        user.id, 
        SettingsUpdate(muted_words=words)
    )
    return settings.muted_words

@router.put("/notifications", response_model=SettingsRead)
async def update_notifications(
    data: SettingsUpdate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Update notification settings"""
    # Only process notification-related fields
    notification_fields = {
        k: v for k, v in data.dict(exclude_unset=True).items()
        if k.startswith('notify_') or k in ['push_enabled', 'email_enabled']
    }
    return await service.update_settings(db, user.id, SettingsUpdate(**notification_fields))

@router.put("/privacy", response_model=SettingsRead)
async def update_privacy(
    data: SettingsUpdate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Update privacy settings"""
    # Only process privacy-related fields
    privacy_fields = {
        k: v for k, v in data.dict(exclude_unset=True).items()
        if k in ['who_can_see_posts', 'who_can_reply', 'allow_messages', 'show_read_receipts']
    }
    return await service.update_settings(db, user.id, SettingsUpdate(**privacy_fields))