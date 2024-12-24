from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class HashtagBase(BaseModel):
    tag: str

    class Config:
        from_attributes = True

class TrendingHashtag(HashtagBase):
    post_count: int
    user_count: int
    trend_score: float
    last_used: datetime
    language: str = Field(default="en")
    first_used: Optional[datetime] = None
    velocity: Optional[float] = None
    engagement_metrics: Dict[str, int] = Field(default_factory=lambda: {
        "likes": 0,
        "shares": 0,
        "comments": 0
    })

class TopicResponse(BaseModel):
    topic: str
    confidence: float
    related_hashtags: List[str]
    language: str = Field(default="en")
    sentiment_score: Optional[float] = None
    subtopics: List[str] = Field(default_factory=list)

class ContentClassification(BaseModel):
    hashtags: List[str]
    topics: List[TopicResponse]
    content_type: str
    language: str = Field(default="en")
    sentiment: Dict[str, float] = Field(default_factory=dict)
    entities: List[Dict[str, str]] = Field(default_factory=list)