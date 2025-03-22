# app/schemas/post_schemas.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class PostResponse(BaseModel):
    """Unified Post Response Schema"""
    model_config = ConfigDict(from_attributes=True)
    
    # Core post data
    id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Author information
    author_id: int
    author_username: str
    
    # Thread context
    thread_id: Optional[int] = None
    position_in_thread: Optional[int] = None
    reply_to_id: Optional[int] = None
    
    # Engagement metrics
    likes_count: int = 0
    view_count: int = 0
    repost_count: int = 0
    unique_viewers: Optional[int] = None
    engagement_score: Optional[float] = None
    is_liked: bool = False
    
    # Search-specific fields
    score: Optional[float] = None  # For search relevance
    
    # Additional metadata
    hashtags: List[str] = []
    mentioned_users: List[str] = []
    last_updated: Optional[datetime] = None

class PostListResponse(BaseModel):
    """Wrapper for list of posts with pagination/metadata"""
    items: List[PostResponse]
    total: int
    type: Optional[str] = None  # For search results: 'semantic', 'text', 'combined'
    has_more: bool = False
    next_cursor: Optional[str] = None  # For cursor-based pagination

def create_post_response(
    post,
    user,
    engagement_data: Optional[dict] = None,
    search_score: Optional[float] = None
) -> PostResponse:
    """Helper function to create unified post response"""
    # Base post data
    response_data = {
        "id": post.id,
        "content": post.content,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "author_id": post.author_id,
        "author_username": user.username,
        "thread_id": post.thread_id,
        "position_in_thread": post.position_in_thread,
        "reply_to_id": post.reply_to_id,
        "likes_count": post.like_count,
        "view_count": post.view_count,
        "repost_count": post.repost_count,
        "hashtags": [tag.tag for tag in post.hashtags] if post.hashtags else [],
        "mentioned_users": [user.username for user in post.mentioned_users] if post.mentioned_users else [],
    }

    # Add engagement data if available
    if engagement_data:
        response_data.update({
            "likes_count": engagement_data.get("likes", post.like_count),
            "view_count": engagement_data.get("views", post.view_count),
            "unique_viewers": engagement_data.get("unique_viewers"),
            "engagement_score": engagement_data.get("engagement_score"),
            "is_liked": engagement_data.get("is_liked", False),
            "last_updated": engagement_data.get("last_updated"),
        })

    # Add search score if available
    if search_score is not None:
        response_data["score"] = search_score

    return PostResponse(**response_data)