"""
TypedDict definitions for MongoDB Post documents.
"""
from typing import TypedDict, Union, Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId

class PostDocument(TypedDict):
    """
    TypedDict definition for a post document in MongoDB.
    Uses MongoDB's native ObjectId for _id instead of PostgreSQL sequences.
    """
    _id: Union[ObjectId, str]
    author_id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime]
    likes_count: int
    views_count: int
    reposts_count: int
    reply_to_id: Optional[Union[ObjectId, str]]
    hashtags: List[str]
    media_urls: Optional[List[str]]
    is_deleted: bool
    is_hidden: bool
    engagement_score: float
    metadata: Dict[str, Any]

class PostEngagementDocument(TypedDict):
    """
    TypedDict definition for post engagement metrics in MongoDB.
    """
    post_id: Union[ObjectId, str]
    likes_count: int
    views_count: int
    reposts_count: int
    comments_count: int
    shares_count: int
    last_updated: datetime
    engagement_score: float

class PostInteractionDocument(TypedDict):
    """
    TypedDict definition for user interactions with posts in MongoDB.
    """
    user_id: int
    post_id: Union[ObjectId, str]
    interaction_type: str  # like, view, repost, comment, share
    timestamp: datetime
    metadata: Optional[Dict[str, Any]]

class PostClassificationDocument(TypedDict):
    """
    TypedDict definition for post content classification in MongoDB.
    """
    post_id: Union[ObjectId, str]
    topics: List[Dict[str, Union[str, float]]]  # [{"topic": "technology", "confidence": 0.95}]
    sentiment: Optional[Dict[str, float]]  # {"positive": 0.8, "negative": 0.1, "neutral": 0.1}
    created_at: datetime
    updated_at: Optional[datetime]
