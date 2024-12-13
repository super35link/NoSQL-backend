from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.auth.dependencies import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from . import service
from .schemas import PostCreate, PostUpdate, ThreadCreate, ThreadUpdate, PostResponse, ThreadResponse
from app.posts.engagement_service import PostEngagementService

router = APIRouter(prefix="/posts", tags=["posts"])

service = service.PostService()

# Post-related endpoints
@router.post("/", response_model=PostResponse)
async def create_post(
    post: PostCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new post"""
    return await service.create_post(session, user.id, post)

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    """Get a specific post by ID"""
    post = await service.get_post(session, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    return post

@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    post_data: PostUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update a post"""
    return await service.update_post(session, user.id, post_id, post_data)

@router.delete("/{post_id}")
async def delete_post(
    post_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a post"""
    return await service.delete_post(session, user.id, post_id)

@router.get("/", response_model=dict)
async def get_posts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    user_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    session: AsyncSession = Depends(get_async_session)
):
    """Get paginated posts with optional filters"""
    return await service.get_posts_paginated(
        session,
        skip=skip,
        limit=limit,
        user_id=user_id,
        thread_id=thread_id
    )

@router.post("/{post_id}/repost", response_model=PostResponse)
async def create_repost(
    post_id: int,
    content: Optional[str] = None,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a repost of an existing post"""
    return await service.create_repost(session, user.id, post_id, content)

# Thread-related endpoints
@router.post("/thread", response_model=ThreadResponse)
async def create_thread(
    thread: ThreadCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create a new thread"""
    return await service.create_thread(session, user.id, thread)

@router.get("/thread/{thread_id}", response_model=dict)
async def get_thread(
    thread_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get a thread with its posts"""
    return await service.get_thread_with_posts(session, thread_id, skip, limit)

@router.patch("/thread/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: int,
    thread_data: ThreadUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Update a thread's settings"""
    return await service.update_thread(session, user.id, thread_id, thread_data)

@router.delete("/thread/{thread_id}")
async def delete_thread(
    thread_id: int,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete a thread and all its posts"""
    return await service.delete_thread(session, user.id, thread_id)

@router.get("/threads", response_model=dict)
async def get_threads(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    user_id: Optional[int] = None,
    session: AsyncSession = Depends(get_async_session)
):
    """Get paginated threads with optional user filter"""
    return await service.get_threads_paginated(session, skip, limit, user_id)

@router.get("/by-username/{username}", response_model=dict)
async def get_posts_by_username(
    username: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get paginated posts by username"""
    return await service.get_posts_by_username(
        session,
        username=username,
        skip=skip,
        limit=limit
    )
    
@router.get("/profile/posts", response_model=dict)
async def get_own_posts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get current user's posts"""
    return await service.get_posts_by_username(
        session,
        username=user.username,
        skip=skip,
        limit=limit
    )
    
@router.get("/by-username/{username}", response_model=dict)
async def get_user_content(
    username: str,
    content_type: str = Query(
        default="posts",
        enum=["posts", "threads", "reposts", "mentions", "collaborations"]
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get different types of post content by username"""
    service_methods = {
        "posts": service.get_posts_by_username,
        "threads": service.get_threads_by_username,
        "reposts": service.get_reposts_by_username,
        "mentions": service.get_mentions_by_username,
        "collaborations": service.get_collaborations_by_username
    }
    
    return await service_methods[content_type](
        session,
        username=username,
        skip=skip,
        limit=limit
    )
    
@router.get("/hashtag/{hashtag}", response_model=dict)
async def get_hashtag_posts(
    hashtag: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    return await service.get_posts_by_hashtag(session, hashtag, skip, limit)

@router.post("/{post_id}/engage")
async def track_post_engagement(
    post_id: int,
    action_type: str = Query(..., enum=["view", "like", "repost"]),
    user: User = Depends(current_active_user)
):
    engagement_service = PostEngagementService()
    await engagement_service.track_engagement(post_id, user.id, action_type)
    return {"status": "success"}

@router.post("/{post_id}/like")
async def toggle_like(
    post_id: int,
    user: User = Depends(current_active_user)
):
    engagement_service = PostEngagementService()
    is_liked = await engagement_service.toggle_like(post_id, user.id)
    return {"liked": is_liked}

@router.get("/{post_id}/stats")
async def get_post_stats(post_id: int):
    engagement_service = PostEngagementService()
    return await engagement_service.get_engagement_stats(post_id)

@router.post("/{post_id}/view")
async def track_view(
    post_id: int,
    user: User = Depends(current_active_user)
):
    engagement_service = PostEngagementService()
    await engagement_service.increment_views(post_id, user.id)
    return {"status": "success"}