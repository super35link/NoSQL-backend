from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl

class ProfileBase(BaseModel):
    bio: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    is_private: bool = False
    show_activity_status: bool = True

class ProfileRead(ProfileBase):
    id: int
    user_id: int
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    profile_views: int
    posts_count: int
    saved_posts_count: int
    media_count: int
    created_at: datetime
    last_active: Optional[datetime] = None

    class Config:
        from_attributes = True

class ProfileUpdate(ProfileBase):
    pass

class ProfilePrivacyUpdate(BaseModel):
    is_private: bool
    show_activity_status: bool

class ProfileStats(BaseModel):
    total_views: int
    total_posts: int
    total_saved: int
    total_media: int
    avg_daily_views: float
    most_active_times: List[str]

class MediaUpload(BaseModel):
    media_type: str  # 'avatar' or 'banner'
    media_url: str

class ProfileCollection(BaseModel):
    posts: List[int]  # List of post IDs
    saved_posts: List[int]
    media: List[str]  # List of media URLs