from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel

class EngagementStats(BaseModel):
    likes: int = 0
    views: int = 0
    unique_viewers: int = 0
    reposts: int = 0
    last_engagement: Optional[datetime] = None
    post_id: str
    likes_count: int
    views_count: int
    reposts_count: int
    comments_count: int
    shares_count: int
    engagement_score: float
    last_updated: str

class UserEngagement(BaseModel):
    has_liked: bool = False
    has_viewed: bool = False
    has_reposted: bool = False

class UserInteraction(BaseModel):
    user_id: int
    post_id: str
    interaction_type: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None