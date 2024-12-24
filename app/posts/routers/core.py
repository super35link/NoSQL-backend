from fastapi import APIRouter, Body, Depends, HTTPException, Path, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.auth.dependencies import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from app.posts.services.core_post_service import EnhancedCorePostService
from app.posts.schemas.post_schemas import PostCreate, PostUpdate, PostResponse

router = APIRouter(prefix="/posts", tags=["posts"])
service = EnhancedCorePostService()

@router.post(
    "/",
    response_model=PostResponse,
    status_code=201,
    responses={
        400: {"description": "Invalid post content"}
    },
    summary="Create a New Post",
    description="Create a new post. Only authenticated users can create a new post."
)
async def create_post(
    post: PostCreate = Body(..., description="The post content to create"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Create a new post.

    Parameters:
    - post: The post content to create.

    Returns:
    - PostResponse: An object containing the details of the created post.

    Raises:
    - 400: If the post content is invalid.
    """
    return await service.create_post(session, user.id, post)

@router.get(
    "/{post_id}",
    response_model=PostResponse,
    responses={
        404: {"description": "Post not found"}
    },
    summary="Get Post Details",
    description="Get details of a specific post."
)
async def get_post(
    post_id: int = Path(..., description="The ID of the post"),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get details of a specific post.

    Parameters:
    - post_id (int): The ID of the post.

    Returns:
    - PostResponse: An object containing the details of the post.

    Raises:
    - 404: If the post does not exist.
    """
    post = await service.get_post(session, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@router.patch(
    "/{post_id}",
    response_model=PostResponse,
    responses={
        404: {"description": "Post not found"},
        403: {"description": "Not authorized to update the post"},
        400: {"description": "Invalid post content"}
    },
    summary="Update Post",
    description="Update a specific post. Only the post creator can update the post."
)
async def update_post(
    post_id: int = Path(..., description="The ID of the post to update"),
    post_data: PostUpdate = Body(..., description="The updated post content"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Update a specific post.

    Parameters:
    - post_id (int): The ID of the post to update.
    - post_data: The updated post content.

    Returns:
    - PostResponse: An object containing the details of the updated post.

    Raises:
    - 404: If the post does not exist.
    - 403: If the user is not authorized to update the post.
    - 400: If the post content is invalid.
    """
    return await service.update_post(session, user.id, post_id, post_data)

@router.delete(
    "/{post_id}",
    responses={
        404: {"description": "Post not found"},
        403: {"description": "Not authorized to delete the post"}
    },
    summary="Delete Post",
    description="Delete a specific post. Only the post creator can delete the post."
)
async def delete_post(
    post_id: int = Path(..., description="The ID of the post to delete"),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Delete a specific post.

    Parameters:
    - post_id (int): The ID of the post to delete.

    Returns:
    - None

    Raises:
    - 404: If the post does not exist.
    - 403: If the user is not authorized to delete the post.
    """
    return await service.delete_post(session, user.id, post_id)