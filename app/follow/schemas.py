from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, constr, field_validator

class FollowBase(BaseModel):
    """Base class for follow operations"""
    status: str = "active"  # active, muted, blocked

class FollowRead(FollowBase):
    """Schema for reading follow relationships"""
    id: int
    follower_id: int
    follower_username: str  # Changed from Username type to str
    following_id: int
    following_username: str  # Changed from Username type to str
    created_at: datetime

    class Config:
        from_attributes = True

class FollowCreate(FollowBase):
    username_to_follow: str

    @field_validator('username_to_follow')
    def validate_username(cls, v):
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        if not v.isalnum() and '_' not in v:
            raise ValueError('Username can only contain letters, numbers, and underscores')
        if len(v) > 50:
            raise ValueError('Username cannot be longer than 50 characters')
        return v

class FollowUpdate(FollowBase):
    """Schema for updating follow status"""
    status: Optional[str]
    target_username: str  # Changed from Username type to str

class FollowStats(BaseModel):
    """Schema for follow statistics"""
    username: str  # Changed from Username type to str
    followers_count: int
    following_count: int
    followers: List[str] = []
    following: List[str] = []

class FollowList(BaseModel):
    """Schema for listing followers/following"""
    users: List[dict] = []
    total_count: int
    page: int
    has_more: bool