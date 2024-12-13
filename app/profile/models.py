from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, JSON, Table
from sqlalchemy.orm import relationship
from app.db.base import Base

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # Basic Info
    avatar_url = Column(String, nullable=True)
    banner_url = Column(String, nullable=True)
    bio = Column(String(500), nullable=True)
    location = Column(String, nullable=True)
    website = Column(String, nullable=True)
    
    # Privacy Settings
    is_private = Column(Boolean, default=False)
    show_activity_status = Column(Boolean, default=True)
    
    # Analytics
    profile_views = Column(Integer, default=0)
    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)
    
    # Collections counters
    posts_count = Column(Integer, default=0)
    saved_posts_count = Column(Integer, default=0)
    media_count = Column(Integer, default=0)

# Blocked Users Association Table
blocked_users = Table(
    'blocked_users',
    Base.metadata,
    Column('blocker_id', Integer, ForeignKey('profiles.id'), primary_key=True),
    Column('blocked_id', Integer, ForeignKey('profiles.id'), primary_key=True)
)

# Profile Views Table
class ProfileView(Base):
    __tablename__ = "profile_views"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"))
    viewer_id = Column(Integer, ForeignKey("users.id"))
    viewed_at = Column(DateTime, default=datetime.now)

# Profile Media Table
class ProfileMedia(Base):
    __tablename__ = "profile_media"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"))
    media_type = Column(String)  # 'avatar' or 'banner'
    media_url = Column(String)
    uploaded_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)  # for tracking media history