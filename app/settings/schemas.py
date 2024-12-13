from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class SettingsBase(BaseModel):
    # Display Settings
    language: Optional[str] = "en"
    theme: Optional[str] = "system"
    timezone: Optional[str] = "UTC"
    autoplay_videos: Optional[bool] = True

    # Privacy Settings
    who_can_see_posts: Optional[str] = "everyone"
    who_can_reply: Optional[str] = "everyone"
    allow_messages: Optional[bool] = True
    show_read_receipts: Optional[bool] = True

    # Notification Settings
    notify_new_followers: Optional[bool] = True
    notify_likes: Optional[bool] = True
    notify_reposts: Optional[bool] = True
    notify_mentions: Optional[bool] = True
    notify_replies: Optional[bool] = True
    push_enabled: Optional[bool] = True
    email_enabled: Optional[bool] = True

    # Content Preferences
    sensitive_content: Optional[bool] = False
    quality_filter: Optional[bool] = True
    muted_words: Optional[List[str]] = []

class SettingsRead(SettingsBase):
    id: int
    user_id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class SettingsUpdate(BaseModel):
    # Display Settings
    language: Optional[str] = None
    theme: Optional[str] = None
    timezone: Optional[str] = None
    autoplay_videos: Optional[bool] = None

    # Privacy Settings
    who_can_see_posts: Optional[str] = None
    who_can_reply: Optional[str] = None
    allow_messages: Optional[bool] = None
    show_read_receipts: Optional[bool] = None

    # Notification Settings
    notify_new_followers: Optional[bool] = None
    notify_likes: Optional[bool] = None
    notify_reposts: Optional[bool] = None
    notify_mentions: Optional[bool] = None
    notify_replies: Optional[bool] = None
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None

    # Content Preferences
    sensitive_content: Optional[bool] = None
    quality_filter: Optional[bool] = None
    muted_words: Optional[List[str]] = None