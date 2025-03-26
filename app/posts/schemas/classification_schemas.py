from datetime import datetime
from typing import Any, List, Dict, Optional, Union
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
    
class TopicItem(BaseModel):
    """Schema for a topic classification item."""
    topic: str
    confidence: float

class SentimentScores(BaseModel):
    """Schema for sentiment analysis scores."""
    positive: float
    negative: float
    neutral: float

class ClassificationRequest(BaseModel):
    """Schema for classification request."""
    topics: List[Dict[str, Union[str, float]]]
    sentiment: Optional[Dict[str, float]] = None

class ClassificationResponse(BaseModel):
    """Schema for classification response."""
    post_id: str
    topics: List[TopicItem]
    sentiment: Optional[SentimentScores] = None
    created_at: str
    updated_at: Optional[str] = None

'''remember to create a  dedicated Schema for hashtag'''

class HashtagResponse(BaseModel):
    """Schema for hashtag response."""
    tag: str
    post_count: int
    follower_count: int

class HashtagPostsResponse(BaseModel):
    """Schema for hashtag posts response."""
    tag: str
    posts: List[Dict[str, Any]]
    total_count: int