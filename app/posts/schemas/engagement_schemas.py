from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class EngagementStats(BaseModel):
    likes: int = 0
    views: int = 0
    unique_viewers: int = 0
    reposts: int = 0
    last_engagement: Optional[datetime] = None

class UserEngagement(BaseModel):
    has_liked: bool = False
    has_viewed: bool = False
    has_reposted: bool = False