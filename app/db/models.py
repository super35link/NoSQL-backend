# app/db/models.py
from datetime import datetime
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, ARRAY, func
from sqlalchemy.orm import relationship, Mapped
from app.db.base import Base
from app.db.associated_tables import post_mentions, post_hashtags
from enum import Enum
from sqlalchemy import Enum as SQLAlchemyEnum




class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"
    id: Mapped[int] = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username: Mapped[str] = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, onupdate=func.now(), nullable=True)
    
    posts = relationship("Post", back_populates="author")
    mentioned_in = relationship("Post", secondary=post_mentions, back_populates="mentioned_users")
    threads = relationship("Thread", back_populates="author")
    

class ThreadStatus(Enum):
    ACTIVE = "active"      # Thread is ongoing, can add more posts
    COMPLETE = "complete"  # Thread is finished, no more posts allowed
class Thread(Base):
    __tablename__ = 'threads'

    id = Column(Integer, primary_key=True, index=True)
    creator_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    status = Column(SQLAlchemyEnum(ThreadStatus), default=ThreadStatus.ACTIVE)
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
    author = relationship("User", foreign_keys=[author_id], back_populates="posts")
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

