# app/posts/routers/thread.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.auth.dependencies import current_active_user
from app.db.base import get_async_session
from app.db.models import User, ThreadStatus
from app.posts.services.thread_service import ThreadService
from app.posts.schemas.thread_schemas import (
    PostCreate,
    PostResponse,
    ThreadPostList,
    ThreadStatusResponse,
    ThreadWithFirstPost
)

router = APIRouter(prefix="/threads", tags=["threads"])
thread_service = ThreadService()

@router.post("/", response_model=dict)
async def start_thread(
    initial_post: PostCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Start a new thread with initial post"""
    return await thread_service.start_thread(session, user.id, initial_post)

@router.post("/{thread_id}/posts", response_model=PostResponse)
async def add_to_thread(
    thread_id: int,
    post: PostCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Add a new post to an existing thread"""
    return await thread_service.add_to_thread(
        session, user.id, thread_id, post.content
    )

@router.patch("/{thread_id}/complete", response_model=ThreadStatusResponse)
async def complete_thread(
    thread_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Mark a thread as complete"""
    return await thread_service.complete_thread(session, user.id, thread_id)

@router.patch("/{thread_id}/reactivate", response_model=ThreadStatusResponse)
async def reactivate_thread(
    thread_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Reactivate a completed thread"""
    return await thread_service.reactivate_thread(session, user.id, thread_id)

@router.get("/{thread_id}/posts", response_model=ThreadPostList)
async def get_thread_posts(
    thread_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all posts in a thread"""
    return await thread_service.get_thread_posts(
        session, thread_id, skip, limit
    )

@router.delete("/{thread_id}/posts/{post_id}")
async def delete_thread_post(
    thread_id: int,
    post_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a post from a thread"""
    return await thread_service.delete_from_thread(
        session, user.id, thread_id, post_id
    )

@router.get("/user", response_model=dict)
async def get_user_threads(
    status: Optional[ThreadStatus] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get threads created by the current user"""
    return await thread_service.get_user_threads(
        session, user.id, status, skip, limit
    )
    
@router.get("/{thread_id}", response_model=ThreadWithFirstPost)
async def get_thread(
    thread_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    """Get thread details with its first post"""
    thread = await thread_service.get_user_threads(
        session, 
        thread_id=thread_id, 
        limit=1
    )
    if not thread or not thread["items"]:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    thread_data = thread["items"][0]  # Get first item since we limited to 1
    return {
        "thread_id": thread_data["thread_id"],
        "status": thread_data["status"],
        "created_at": thread_data["created_at"],
        "completed_at": thread_data.get("completed_at"),
        "creator_username": thread_data["creator_username"],
        "first_post": thread_data["first_post"]
    }