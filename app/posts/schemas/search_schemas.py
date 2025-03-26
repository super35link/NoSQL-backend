from datetime import datetime
from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict

class SearchFilters(BaseModel):
    model_config = ConfigDict(strict=True)

    author_id: Optional[int] = None
    hashtags: Optional[List[str]] = Field(default=None, max_items=10)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_likes: Optional[int] = Field(default=None, ge=0)
    content_type: Optional[str] = Field(default=None, pattern="^(post|thread|reply)$")
    min_score: Optional[float] = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator('hashtags')
    @classmethod
    def validate_hashtags(cls, hashtags: Optional[List[str]]) -> Optional[List[str]]:
        if hashtags is None:
            return None
        for tag in hashtags:
            if not tag.isalnum():
                raise ValueError('Hashtags must be alphanumeric')
            if len(tag) > 50:
                raise ValueError('Hashtag too long')
        return hashtags

    @field_validator('date_to')
    @classmethod
    def validate_date_range(cls, v: Optional[datetime], info) -> Optional[datetime]:
        if v and info.data.get('date_from'):
            if info.data['date_from'] > v:
                raise ValueError('date_to must be after date_from')
        return v

class SearchResult(BaseModel):
    model_config = ConfigDict(strict=True)
    post_id: int
    content: str
    author_username: str
    created_at: datetime
    relevance_score: float
    hashtags: List[str]
    engagement_metrics: Dict[str, int]

class SearchParams(BaseModel):
    model_config = ConfigDict(strict=True)

    query: str
    query_vector: Optional[List[float]] = Field(None, min_items=384, max_items=384)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    filters: Optional[SearchFilters] = None
    search_type: str = Field(default="combined", pattern="^(semantic|text|combined)$")
    

class SearchResponse(BaseModel):
    query: str
    posts: List[Dict[str, Any]]
    total_count: int
    execution_time_ms: float