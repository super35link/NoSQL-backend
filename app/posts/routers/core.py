from typing import Any, Dict
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.users import current_active_user
from app.db.base import get_async_session
from app.db.models import User
from app.db.redis import redis_manager
from app.posts.services.core_post_service import EnhancedCorePostService, PostCache, PostValidator
from app.posts.schemas.post_schemas import PostCreate, PostUpdate, PostResponse
from app.posts.schemas.engagement_schemas import EngagementStats, UserEngagement
import asyncio

from app.posts.services.engagement_service import PostEngagementService

router = APIRouter(prefix="/posts", tags=["posts"])
# 1. First create the PostCache with the redis_manager
cache = PostCache(redis_manager, cache_ttl=3600)
# 2. Create the validator with the redis_manager
validator = PostValidator(redis_manager)
# 3. Create the service with both cache and validator
service = EnhancedCorePostService(cache, validator) 


# Start the periodic flush task
asyncio.create_task(redis_manager.start_periodic_flush())

@router.post(
    "/create",
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
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)
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
    # Record view when getting post details
    await redis_manager.increment_interaction(post_id, "view", current_user.id)
    
    post = await service.get_post(session, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Check if user has liked the post
    post_dict = dict(post)
    post_dict["is_liked"] = await redis_manager.check_user_interaction(post_id, "like", current_user.id)
    
    return post_dict

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

# Add new endpoints for interactions

@router.post(
    "/{post_id}/like",
    response_model=dict,
    summary="Like or Unlike a Post",
    description="Toggle like status for a post. If the post is already liked, it will be unliked."
)
async def like_post(
    post_id: int = Path(..., description="The ID of the post to like/unlike"),
    user: User = Depends(current_active_user)
):
    """
    Like or unlike a post.
    
    This is a toggle operation - if the post is already liked by the user,
    it will be unliked. If not, it will be liked.
    
    Parameters:
    - post_id (int): The ID of the post to like/unlike.
    
    Returns:
    - A dictionary with the new like status
    """
    # Check current like status
    is_liked = await redis_manager.check_user_interaction(post_id, "like", user.id)
    
    if is_liked:
        # Unlike the post
        await redis_manager.remove_interaction(post_id, "like", user.id)
        return {"status": "unliked"}
    else:
        # Like the post
        await redis_manager.increment_interaction(post_id, "like", user.id)
        return {"status": "liked"}

@router.post(
    "/{post_id}/view",
    status_code=204,
    summary="Record Post View",
    description="Record that a user has viewed a post."
)
async def record_view(
    post_id: int = Path(..., description="The ID of the post viewed"),
    user: User = Depends(current_active_user)
):
    """
    Record that a user has viewed a post.
    
    Parameters:
    - post_id (int): The ID of the post viewed.
    
    Returns:
    - No content (204)
    """
    await redis_manager.increment_interaction(post_id, "view", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post(
    "/{post_id}/repost",
    response_model=dict,
    summary="Repost or Un-repost a Post",
    description="Toggle repost status for a post."
)
async def repost_post(
    post_id: int = Path(..., description="The ID of the post to repost/un-repost"),
    user: User = Depends(current_active_user)
):
    """
    Repost or un-repost a post.
    
    This is a toggle operation - if the post is already reposted by the user,
    it will be un-reposted. If not, it will be reposted.
    
    Parameters:
    - post_id (int): The ID of the post to repost/un-repost.
    
    Returns:
    - A dictionary with the new repost status
    """
    # Check current repost status
    is_reposted = await redis_manager.check_user_interaction(post_id, "repost", user.id)
    
    if is_reposted:
        # Un-repost the post
        await redis_manager.remove_interaction(post_id, "repost", user.id)
        return {"status": "un-reposted"}
    else:
        # Repost the post
        await redis_manager.increment_interaction(post_id, "repost", user.id)
        return {"status": "reposted"}

@router.get(
    "/{post_id}/engagement",
    response_model=EngagementStats,
    summary="Get Post Engagement Stats",
    description="Get engagement statistics for a post."
)
async def get_post_engagement(
    post_id: int = Path(..., description="The ID of the post"),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get engagement statistics for a post.
    
    Parameters:
    - post_id (int): The ID of the post.
    
    Returns:
    - EngagementStats: An object containing engagement statistics.
    
    Raises:
    - 404: If the post does not exist.
    """
    # Get post from database (source of truth for counts)
    post = await service.get_post(session, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Return the engagement stats
    return EngagementStats(
        likes=post.like_count,
        views=post.view_count,
        reposts=post.repost_count
    )

@router.get(
    "/{post_id}/engagement/user",
    response_model=UserEngagement,
    summary="Get User's Engagement with Post",
    description="Get the current user's engagement with a specific post."
)
async def get_user_engagement(
    post_id: int = Path(..., description="The ID of the post"),
    user: User = Depends(current_active_user)
):
    """
    Get the current user's engagement with a specific post.
    
    Parameters:
    - post_id (int): The ID of the post.
    
    Returns:
    - UserEngagement: An object containing the user's engagement with the post.
    """
    # Check user interactions
    has_liked = await redis_manager.check_user_interaction(post_id, "like", user.id)
    has_viewed = await redis_manager.check_user_interaction(post_id, "view", user.id)
    has_reposted = await redis_manager.check_user_interaction(post_id, "repost", user.id)
    
    return UserEngagement(
        has_liked=has_liked,
        has_viewed=has_viewed,
        has_reposted=has_reposted
    )
    
@router.get(
    "/batch-stats/{post_ids}",
    response_model=Dict[str, Any],
    summary="Get Batch Engagement Stats",
    description="Get engagement statistics for multiple posts in a single request."
)
async def get_batch_engagement_stats(
    post_ids: str = Path(..., description="Comma-separated list of post IDs"),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get engagement statistics for multiple posts in a single request.
    
    Parameters:
    - post_ids: Comma-separated list of post IDs (e.g., "1,2,3,4,5")
    
    Returns:
    - A dictionary mapping post IDs to their engagement statistics
    """
    post_id_list = [int(id.strip()) for id in post_ids.split(',') if id.strip().isdigit()]
    
    if not post_id_list:
        return {}
        
    engagement_service = PostEngagementService(db)
    
    # Get stats for all posts in a single MongoDB query
    stats = await engagement_service.get_batch_engagement_stats(post_id_list, user.id)
    
    return stats