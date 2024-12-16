from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class SearchFilters(BaseModel):
    author_id: Optional[int] = None
    hashtags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_likes: Optional[int] = None
    content_type: Optional[str] = None

class SearchResult(BaseModel):
    post_id: int
    content: str
    author_username: str
    created_at: datetime
    relevance_score: float
    hashtags: List[str]
    engagement_metrics: dict