# app/posts/routers/thread.py
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.auth.dependencies import current_active_user
from app.db.base import get_async_session
from app.db.models import User, ThreadStatus
from app.posts.services.thread_service import ThreadService
from app.posts.schemas.thread_schemas import (
    PostCreate,
    PostResponse,
    ThreadListResponse,
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


@router.delete(
    "/{thread_id}/posts/{post_id}",
    responses={
        404: {"description": "Post or thread not found"},
        403: {"description": "Not authorized to delete the post"}
    },
    summary="Delete Post from Thread",
    description="Delete a post from a specific thread. Only the post creator or thread creator can delete the post."
)
async def delete_thread_post(
    thread_id: int = Path(..., description="The ID of the thread"),
    post_id: int = Path(..., description="The ID of the post to delete"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Delete a post from a specific thread.

    Parameters:
    - thread_id (int): The ID of the thread.
    - post_id (int): The ID of the post to delete.

    Returns:
    - None

    Raises:
    - 404: If the post or thread does not exist.
    - 403: If the user is not authorized to delete the post.
    """
    return await thread_service.delete_from_thread(session, user.id, thread_id, post_id)

@router.get(
    "/user",
    response_model=ThreadListResponse,
    summary="Get Threads Created by User",
    description="Get all threads created by the current user."
)
async def get_user_threads(
    status: Optional[ThreadStatus] = Query(None, description="Filter threads by status"),
    skip: int = Query(default=0, ge=0, description="Number of threads to skip"),
    limit: int = Query(default=20, le=100, description="Maximum number of threads to return"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get all threads created by the current user.

    Parameters:
    - status (ThreadStatus, optional): Filter threads by status.
    - skip (int): Number of threads to skip.
    - limit (int): Maximum number of threads to return.

    Returns:
    - ThreadListResponse: An object containing the list of threads created by the user.
    """
    return await thread_service.get_user_threads(session, user.id, status, skip, limit)

    
@router.get(
    "/{thread_id}",
    response_model=ThreadWithFirstPost,
    responses={
        404: {"description": "Thread not found"}
    },
    summary="Get Thread Details",
    description="Get details of a specific thread including its first post."
)
async def get_thread(
    thread_id: int = Path(..., description="The ID of the thread"),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get details of a specific thread including its first post.

    Parameters:
    - thread_id (int): The ID of the thread.

    Returns:
    - ThreadWithFirstPost: An object containing the details of the thread and its first post.

    Raises:
    - 404: If the thread does not exist.
    """
    thread = await thread_service.get_thread(session, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread