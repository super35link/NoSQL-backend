# app/schemas/post_schemas.py
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from bson import ObjectId

class PostResponse(BaseModel):
    """Unified Post Response Schema"""
    model_config = ConfigDict(from_attributes=True)
    
    # Core post data
    id: str  # Changed from int to str to accommodate MongoDB's ObjectId
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Author information
    author_id: int
    author_username: str
    
    # Thread context
    thread_id: Optional[str] = None  # Changed from int to str
    position_in_thread: Optional[int] = None
    reply_to_id: Optional[str] = None  # Changed from int to str
    
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
    post: Dict[str, Any],
    user: Dict[str, Any],
    engagement_data: Optional[Dict[str, Any]] = None,
    search_score: Optional[float] = None
) -> PostResponse:
    """
    Helper function to create unified post response from MongoDB document
    
    Args:
        post: MongoDB post document with _id field
        user: MongoDB user document with username field
        engagement_data: Optional engagement statistics
        search_score: Optional search relevance score
        
    Returns:
        PostResponse object with properly mapped fields
    """
    # Base post data with safe access using .get() with defaults
    # Properly convert ObjectId to string where needed
    post_id = post.get("_id", "")
    post_id_str = str(post_id) if isinstance(post_id, ObjectId) else post_id
    
    thread_id = post.get("thread_id")
    thread_id_str = str(thread_id) if isinstance(thread_id, ObjectId) else thread_id
    
    reply_to_id = post.get("reply_to_id")
    reply_to_id_str = str(reply_to_id) if isinstance(reply_to_id, ObjectId) else reply_to_id
    
    response_data = {
        "id": post_id_str,
        "content": post.get("content", ""),
        "created_at": post.get("created_at", datetime.utcnow()),
        "updated_at": post.get("updated_at"),
        "author_id": post.get("author_id"),
        "author_username": user.get("username", ""),
        "thread_id": thread_id_str if thread_id else None,
        "position_in_thread": post.get("position_in_thread"),
        "reply_to_id": reply_to_id_str if reply_to_id else None,
        "likes_count": post.get("likes_count", 0),
        "view_count": post.get("views_count", 0),  # Note: field name difference
        "repost_count": post.get("reposts_count", 0),  # Note: field name difference
        "hashtags": post.get("hashtags", []),
        "mentioned_users": post.get("mentioned_users", []),
    }

    # Add engagement data if available (with proper field mapping)
    if engagement_data:
        response_data.update({
            "likes_count": engagement_data.get("likes", post.get("likes_count", 0)),
            "view_count": engagement_data.get("views", post.get("views_count", 0)),
            "unique_viewers": engagement_data.get("unique_viewers"),
            "engagement_score": engagement_data.get("engagement_score"),
            "is_liked": engagement_data.get("is_liked", False),
            "last_updated": engagement_data.get("last_updated"),
        })

    # Add search score if available
    if search_score is not None:
        response_data["score"] = search_score

    return PostResponse(**response_data)

# Helper function to create a PostResponse list from MongoDB documents
def create_post_responses(
    posts: List[Dict[str, Any]],
    users: Dict[int, Dict[str, Any]],  # Map of user_id -> user document
    engagement_data: Optional[Dict[str, Dict[str, Any]]] = None,  # Map of post_id -> engagement data
    search_scores: Optional[Dict[str, float]] = None  # Map of post_id -> search score
) -> List[PostResponse]:
    """
    Create a list of PostResponse objects from MongoDB documents
    
    Args:
        posts: List of MongoDB post documents
        users: Dictionary mapping user IDs to user documents
        engagement_data: Optional dictionary mapping post IDs to engagement data
        search_scores: Optional dictionary mapping post IDs to search scores
        
    Returns:
        List of PostResponse objects
    """
    responses = []
    
    for post in posts:
        post_id = str(post.get("_id", ""))
        author_id = post.get("author_id")
        user = users.get(author_id, {"username": "unknown"})
        
        engagement = None
        if engagement_data and post_id in engagement_data:
            engagement = engagement_data[post_id]
            
        score = None
        if search_scores and post_id in search_scores:
            score = search_scores[post_id]
            
        response = create_post_response(post, user, engagement, score)
        responses.append(response)
        
    return responses