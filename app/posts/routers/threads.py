# app/posts/routers/thread.py
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
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

@router.post(
    "/",
    response_model=ThreadStatusResponse,
    status_code=201,
    responses={
        400: {"description": "Invalid initial post content"}
    },
    summary="Start a New Thread",
    description="Create a new thread with an initial post. Only authenticated users can start a new thread."
)
async def start_thread(
    initial_post: PostCreate = Body(..., description="The initial post content to start the thread"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Start a new thread with an initial post.

    Parameters:
    - initial_post: The initial post content to start the thread.

    Returns:
    - ThreadResponse: An object containing the details of the created thread.

    Raises:
    - 400: If the initial post content is invalid.
    """
    return await thread_service.start_thread(session, user.id, initial_post)


@router.post(
    "/{thread_id}/posts",
    response_model=PostResponse,
    status_code=201,
    responses={
        404: {"description": "Thread not found"},
        403: {"description": "Not authorized to add to thread"},
        400: {"description": "Invalid post content"}
    },
    summary="Add Post to Thread",
    description="Add a new post to an existing thread. Only the thread creator can add posts."
)
async def add_to_thread(
    thread_id: int = Path(..., description="The ID of the thread to add the post to"),
    post: PostCreate = Body(..., description="The post content to add"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Add a new post to an existing thread.

    Parameters:
    - thread_id (int): The ID of the thread to add the post to.
    - post (PostCreate): The post content and metadata to be added.

    Returns:
    - PostResponse: An object containing the details of the created post.

    Raises:
    - 404: If the thread does not exist.
    - 403: If the user is not authorized to add to the thread.
    - 400: If the post content is invalid.
    """
    return await thread_service.add_to_thread(session, user.id, thread_id, post)


@router.patch(
    "/{thread_id}/complete",
    response_model=ThreadStatusResponse,
    responses={
        404: {"description": "Thread not found"},
        403: {"description": "Not authorized to complete the thread"}
    },
    summary="Complete Thread",
    description="Mark a thread as complete. Only the thread creator can complete a thread."
)
async def complete_thread(
    thread_id: int = Path(..., description="The ID of the thread to complete"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Mark a thread as complete.

    Parameters:
    - thread_id (int): The ID of the thread to complete.

    Returns:
    - ThreadStatusResponse: An object containing the updated thread status.

    Raises:
    - 404: If the thread does not exist.
    - 403: If the user is not authorized to complete the thread.
    """
    return await thread_service.complete_thread(session, user.id, thread_id)


@router.patch(
    "/{thread_id}/reactivate",
    response_model=ThreadStatusResponse,
    responses={
        404: {"description": "Thread not found"},
        403: {"description": "Not authorized to reactivate the thread"}
    },
    summary="Reactivate Thread",
    description="Reactivate a completed thread. Only the thread creator can reactivate a thread."
)
async def reactivate_thread(
    thread_id: int = Path(..., description="The ID of the thread to reactivate"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Reactivate a completed thread.

    Parameters:
    - thread_id (int): The ID of the thread to reactivate.

    Returns:
    - ThreadStatusResponse: An object containing the updated thread status.

    Raises:
    - 404: If the thread does not exist.
    - 403: If the user is not authorized to reactivate the thread.
    """
    return await thread_service.reactivate_thread(session, user.id, thread_id)


@router.get(
    "/{thread_id}/posts",
    response_model=ThreadPostList,
    responses={
        404: {"description": "Thread not found"}
    },
    summary="Get Posts in Thread",
    description="Get all posts in a specific thread."
)
async def get_thread_posts(
    thread_id: int = Path(..., description="The ID of the thread"),
    skip: int = Query(default=0, ge=0, description="Number of posts to skip"),
    limit: int = Query(default=20, le=100, description="Maximum number of posts to return"),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get all posts in a specific thread.

    Parameters:
    - thread_id (int): The ID of the thread.
    - skip (int): Number of posts to skip.
    - limit (int): Maximum number of posts to return.

    Returns:
    - ThreadPostList: An object containing the list of posts in the thread.

    Raises:
    - 404: If the thread does not exist.
    """
    return await thread_service.get_thread_posts(session, thread_id, skip, limit)


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