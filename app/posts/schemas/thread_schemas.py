# app/posts/schemas/thread_schemas.py
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
from pydantic import BaseModel, Field

class ThreadStatus(Enum):
    ACTIVE = "active"
    COMPLETE = "complete"

class PostResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    author_username: str
    thread_id: int
    position_in_thread: int

    class Config:
        from_attributes = True

class PostCreate(BaseModel):
    content: str = Field(..., max_length=500)

class ThreadPostList(BaseModel):
    thread_id: int
    creator_username: str
    created_at: datetime
    posts: List[PostResponse]
    total_posts: int
    skip: int
    limit: int

class ThreadStatusResponse(BaseModel):
    thread_id: int
    status: str
    completed_at: Optional[datetime] = None
    reactivated_at: Optional[datetime] = None

class ThreadWithFirstPost(BaseModel):
    thread_id: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    creator_username: str
    first_post: Dict  # Contains id, content, created_at, author_username