from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.auth.dependencies import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from app.posts.services.core_post_service import CorePostService
from app.posts.schemas import PostCreate, PostUpdate, PostResponse

router = APIRouter(prefix="/posts", tags=["posts"])
service = CorePostService()

@router.post("/", response_model=PostResponse)
async def create_post(
    post: PostCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    return await service.create_post(session, user.id, post)

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    post = await service.get_post(session, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    post_data: PostUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    return await service.update_post(session, user.id, post_id, post_data)

@router.delete("/{post_id}")
async def delete_post(
    post_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    return await service.delete_post(session, user.id, post_id)