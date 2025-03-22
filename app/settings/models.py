from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from app.db.base import Base

class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Display Settings
    language = Column(String, default="en")
    theme = Column(String, default="system")  # light/dark/system
    timezone = Column(String, default="UTC")
    autoplay_videos = Column(Boolean, default=True)
    
    preference = Column(String, nullable=True)
    
    # Privacy Settings
    who_can_see_posts = Column(String, default="everyone")  # everyone/followers/nobody
    who_can_reply = Column(String, default="everyone")      # everyone/followers/mentioned
    allow_messages = Column(Boolean, default=True)
    show_read_receipts = Column(Boolean, default=True)
    
    # Notification Settings
    notify_new_followers = Column(Boolean, default=True)
    notify_likes = Column(Boolean, default=True)
    notify_reposts = Column(Boolean, default=True)
    notify_mentions = Column(Boolean, default=True)
    notify_replies = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)
    
    # Content Preferences
    sensitive_content = Column(Boolean, default=False)
    quality_filter = Column(Boolean, default=True)
    muted_words = Column(JSON, default=list)  # Keep as JSON for flexibility

    # Timestamps
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="settings")

    def __repr__(self):
        return f"<Settings(user_id={self.user_id}, language={self.language})>"