# app/posts/schemas/thread_schemas.py
from datetime import datetime
from typing import Any, Dict, Optional, List
from enum import Enum
from pydantic import BaseModel

from app.posts.schemas.post_response import PostResponse

class ThreadStatus(Enum):
    active = "active"
    complete = "complete"



class ThreadPostList(BaseModel):
    thread_id: int
    creator_username: str
    created_at: datetime
    posts: List[PostResponse]
    total_posts: int
    skip: int
    limit: int

class ThreadResponse(BaseModel):
    thread_id: int
    status: str
    created_at: str
    completed_at: Optional[str] = None
    creator_username: str
    first_post: PostResponse
    root_post: Dict[str, Any]
    replies: List[Dict[str, Any]]
    total_replies: int
    depth: int

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
    first_post: PostResponse  # Contains id, content, created_at, author_username
    
class ThreadListResponse(BaseModel):
    items: List[ThreadResponse]
    total: int
    # Add any other fields required for the thread list response
