from datetime import datetime
from typing import List, Dict
from pydantic import BaseModel

class HashtagBase(BaseModel):
    tag: str

    class Config:
        from_attributes = True

class TrendingHashtag(HashtagBase):
    post_count: int
    user_count: int
    trend_score: float
    last_used: datetime

class TopicResponse(BaseModel):
    topic: str
    confidence: float
    related_hashtags: List[str]

class ContentClassification(BaseModel):
    hashtags: List[str]
    topics: List[TopicResponse]
    content_type: str