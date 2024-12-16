from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class PostBase(BaseModel):
    content: str = Field(..., max_length=500)
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
    like_count: int = 0
    view_count: int = 0
    repost_count: int = 0

    class Config:
        from_attributes = True