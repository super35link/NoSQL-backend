from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.auth.users import current_active_user
from app.db.base import get_async_session
from . import service
from .schemas import ProfileRead, ProfileUpdate, ProfilePrivacyUpdate, ProfileStats, ProfileCollection

router = APIRouter(prefix="/profile", tags=["profile"])

@router.get("/me", response_model=ProfileRead)
async def get_my_profile(
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.get_profile(db, user.id)

@router.get("/{username}", response_model=ProfileRead)
async def get_user_profile(
    username: str,
    current_user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.get_user_profile(db, username, current_user.username)

@router.put("/me", response_model=ProfileRead)
async def update_profile(
    data: ProfileUpdate,
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.update_profile(db, user.id, data)

@router.put("/privacy", response_model=ProfileRead)
async def update_privacy(
    data: ProfilePrivacyUpdate,
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.update_privacy(db, user.id, data)

@router.post("/block/{username}")
async def block_user(
    username: str,
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.block_user(db, user.username, username)

@router.get("/blocked", response_model=List[str])  # Changed from List[int] to List[str]
async def get_blocked_users(
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Returns list of blocked usernames"""
    return await service.get_blocked_users(db, user.username)

@router.get("/stats/{username}", response_model=ProfileStats)
async def get_profile_stats(
    username: str,
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.get_profile_stats(db, username)

@router.post("/media/avatar", response_model=ProfileRead)
async def upload_avatar(
    file: UploadFile = File(...),
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.upload_media(db, user.id, file, "avatar")

@router.post("/media/banner", response_model=ProfileRead)
async def upload_banner(
    file: UploadFile = File(...),
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.upload_media(db, user.id, file, "banner")

@router.get("/{username}/collections", response_model=ProfileCollection)
async def get_collections(
    username: str,
    user = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    return await service.get_collections(db, username)