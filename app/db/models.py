# app/db/models.py
from datetime import datetime
from typing import Optional
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, ARRAY, func
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base import Base
from app.db.associated_tables import post_mentions, post_hashtags
from enum import Enum
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.asyncio import AsyncSession





class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"

    # Override the id field to use Integer instead of UUID
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Required by FastAPI-Users
    email: Mapped[str] = mapped_column(String(length=320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Additional fields
    username: Mapped[str] = mapped_column(String(length=30), unique=True, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True
    )
    async def ensure_settings(self, session: AsyncSession) -> None:
        """Ensure user has associated settings"""
        if not self.settings:
            from app.settings.models import Settings
            self.settings = Settings(user_id=self.id)
            session.add(self.settings)
            await session.commit()
    
    # Relationships
    posts = relationship("Post", back_populates="author")
    mentioned_in = relationship("Post", secondary=post_mentions, back_populates="mentioned_users")
    threads = relationship("Thread", back_populates="author")
     # Relationship with Settings - one-to-one
    settings = relationship("Settings", back_populates="user", uselist=False, cascade="all, delete-orphan")

    # Follow relationships
    user_follows = relationship(
        "Follow",
        foreign_keys="[Follow.follower_id]",
        back_populates="follower"
    )
    user_followers = relationship(
        "Follow",
        foreign_keys="[Follow.following_id]",
        back_populates="following"
    )

    @property
    def following(self):
        """Users that this user follows"""
        return [follow.following for follow in self.user_follows]

    @property
    def followers(self):
        """Users that follow this user"""
        return [follow.follower for follow in self.user_followers]


    def __repr__(self):
        return f"User(id={self.id}, email={self.email}, username={self.username})"
    async def ensure_settings(self, session):
        """Ensure user has associated settings"""
        if not self.settings:
            from app.settings.models import Settings
            self.settings = Settings(user_id=self.id)
            session.add(self.settings)
            await session.commit()
 
class ThreadStatus(Enum):
    active = "active"      # Thread is ongoing, can add more posts
    complete = "complete"  # Thread is finished, no more posts allowed
class Thread(Base):
    __tablename__ = 'threads'

    id = Column(Integer, primary_key=True, index=True)
    creator_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    status = Column(SQLAlchemyEnum(ThreadStatus), default=ThreadStatus.active)
    completed_at: Mapped[datetime] = Column(DateTime, nullable=True)

    # Relationships
    author = relationship("User", foreign_keys=[creator_id], back_populates="threads")
    posts = relationship("Post", back_populates="thread")



class Post(Base):
    __tablename__ = 'posts'

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    content: Mapped [str] = Column(String(500), nullable=False)
    author_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = Column(DateTime, onupdate=datetime.utcnow, nullable=True)

    # Thread fields
    thread_id: Mapped[int] = Column(Integer, ForeignKey('threads.id', ondelete='CASCADE'), nullable=True)
    position_in_thread: Mapped[int] = Column(Integer, nullable=True)

    # Reply fields
    reply_to_id: Mapped[int] = Column(Integer, ForeignKey('posts.id', ondelete='SET NULL'), nullable=True)

    # Vector field for semantic search
    content_vector = Column(ARRAY(Float), nullable=True)

    # Engagement metrics
    like_count: Mapped[int] = Column(Integer, default=0)
    view_count: Mapped[int] = Column(Integer, default=0)
    repost_count: Mapped[int] = Column(Integer, default=0)

    # Relationships
    author: Mapped["User"] = relationship(
        "User", 
        foreign_keys=[author_id], 
        back_populates="posts"
    )
    thread = relationship("Thread", back_populates="posts")
    replies = relationship(
        "Post",
        foreign_keys=[reply_to_id],
        remote_side=[id]
    )
    hashtags = relationship("Hashtag", secondary=post_hashtags)
    mentioned_users = relationship("User", secondary=post_mentions)

class Hashtag(Base):
    __tablename__ = 'hashtags'

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    tag: Mapped [str] = Column(String, unique=True, index=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    usage_count: Mapped[int] = Column(Integer, default=0)

    # Relationships
    posts = relationship("Post", secondary=post_hashtags)

