"""
MongoDB implementation of engagement router.
Replaces the SQL-dependent implementation with MongoDB.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from app.posts.services.nosql_core_post_service import NoSQLCorePostService
from app.auth.users import current_active_user
from app.db.models import User

router = APIRouter()

# Initialize the NoSQL post service
nosql_post_service = NoSQLCorePostService()

class EngagementStats(BaseModel):
    """Schema for engagement statistics."""
    post_id: str
    likes_count: int
    views_count: int
    reposts_count: int
    comments_count: int
    shares_count: int
    engagement_score: float
    last_updated: str

class UserInteraction(BaseModel):
    """Schema for user interaction."""
    user_id: int
    post_id: str
    interaction_type: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None

@router.get("/posts/{post_id}/engagement", response_model=EngagementStats)
async def get_post_engagement(
    post_id: str,
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get engagement statistics for a post using MongoDB.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Get post to verify it exists
    post = await nosql_post_service.get_post(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Get engagement stats
    try:
        post_id_obj = nosql_post_service.db.ObjectId(post_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )
    
    engagement = await nosql_post_service.db.post_engagements.find_one({"post_id": post_id_obj})
    
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement statistics not found"
        )
    
    # Format response
    return EngagementStats(
        post_id=post_id,
        likes_count=engagement.get("likes_count", 0),
        views_count=engagement.get("views_count", 0),
        reposts_count=engagement.get("reposts_count", 0),
        comments_count=engagement.get("comments_count", 0),
        shares_count=engagement.get("shares_count", 0),
        engagement_score=engagement.get("engagement_score", 0.0),
        last_updated=engagement["last_updated"].isoformat()
    )

@router.get("/posts/{post_id}/interactions", response_model=List[UserInteraction])
async def get_post_interactions(
    post_id: str,
    interaction_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(current_active_user)
):
    """
    Get user interactions for a post using MongoDB.
    Admin or post owner only.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Get post to verify it exists and check ownership
    post = await nosql_post_service.get_post(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Check if user is the author or has admin privileges
    if post["author_id"] != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view post interactions"
        )
    
    # Build query
    try:
        post_id_obj = nosql_post_service.db.ObjectId(post_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )
    
    query = {"post_id": post_id_obj}
    if interaction_type:
        query["interaction_type"] = interaction_type
    
    # Get interactions
    cursor = nosql_post_service.db.post_interactions.find(query).sort(
        "timestamp", -1
    ).skip(skip).limit(limit)
    
    interactions = []
    async for interaction in cursor:
        interactions.append(UserInteraction(
            user_id=interaction["user_id"],
            post_id=str(interaction["post_id"]),
            interaction_type=interaction["interaction_type"],
            timestamp=interaction["timestamp"].isoformat(),
            metadata=interaction.get("metadata")
        ))
    
    return interactions

@router.get("/users/{user_id}/interactions", response_model=List[UserInteraction])
async def get_user_interactions(
    user_id: int,
    interaction_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(current_active_user)
):
    """
    Get interactions by a specific user using MongoDB.
    Admin or the user themselves only.
    """
    # Check if user is requesting their own interactions or has admin privileges
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view other users' interactions"
        )
    
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Build query
    query = {"user_id": user_id}
    if interaction_type:
        query["interaction_type"] = interaction_type
    
    # Get interactions
    cursor = nosql_post_service.db.post_interactions.find(query).sort(
        "timestamp", -1
    ).skip(skip).limit(limit)
    
    interactions = []
    async for interaction in cursor:
        interactions.append(UserInteraction(
            user_id=interaction["user_id"],
            post_id=str(interaction["post_id"]),
            interaction_type=interaction["interaction_type"],
            timestamp=interaction["timestamp"].isoformat(),
            metadata=interaction.get("metadata")
        ))
    
    return interactions

@router.get("/trending/posts", response_model=List[Dict[str, Any]])
async def get_trending_posts(
    time_period: str = Query("day", description="Time period for trending posts: hour, day, week, month"),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get trending posts based on engagement score using MongoDB.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Calculate time threshold based on time_period
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    
    if time_period == "hour":
        threshold = now - timedelta(hours=1)
    elif time_period == "day":
        threshold = now - timedelta(days=1)
    elif time_period == "week":
        threshold = now - timedelta(weeks=1)
    elif time_period == "month":
        threshold = now - timedelta(days=30)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid time period. Use hour, day, week, or month."
        )
    
    # Get post IDs with highest engagement scores
    cursor = nosql_post_service.db.post_engagements.find({
        "last_updated": {"$gte": threshold}
    }).sort("engagement_score", -1).limit(limit)
    
    post_ids = []
    async for engagement in cursor:
        post_ids.append(engagement["post_id"])
    
    # Get posts by IDs
    trending_posts = []
    for post_id in post_ids:
        post = await nosql_post_service.get_post(str(post_id))
        if post and not post["is_deleted"] and not post["is_hidden"]:
            trending_posts.append(post)
    
    return trending_posts
