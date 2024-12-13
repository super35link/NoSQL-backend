from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class HashtagBase(BaseModel):
    tag: str

    class Config:
        from_attributes = True

class PostBase(BaseModel):
    content: str = Field(..., max_length=500)
    thread_id: Optional[int] = None
    reply_to_id: Optional[int] = None

    class Config:
        from_attributes = True

class PostCreate(PostBase):
    pass

class PostUpdate(BaseModel):
    content: Optional[str] = Field(None, max_length=500)

class PostResponse(PostBase):
    id: int
    created_at: datetime
    author_username: str
    position_in_thread: Optional[int]
    like_count: int
    repost_count: int

    class Config:
        from_attributes = True

class ThreadBase(BaseModel):
    is_collaborative: bool = False

    class Config:
        from_attributes = True

class ThreadCreate(ThreadBase):
    posts: List[str]  # List of post contents for thread

class ThreadUpdate(BaseModel):
    is_collaborative: Optional[bool] = None

class ThreadResponse(ThreadBase):
    id: int
    creator_username: str
    created_at: datetime
    posts: List[PostResponse] = []

    class Config:
        from_attributes = True