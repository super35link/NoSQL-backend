# post_generator.py
from pathlib import Path
import typer
from typing import Optional
import textwrap

app = typer.Typer()

class PostModuleGenerator:
    def __init__(self, base_path: str = "app"):
        self.base_path = Path(base_path)
        self.module_path = self.base_path / "post"
        
    def generate_model(self) -> str:
        return textwrap.dedent('''
            from datetime import datetime
            from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Boolean, Float
            from sqlalchemy.orm import relationship
            from sqlalchemy.dialects.postgresql import ARRAY
            from app.db.base import Base

            # Association tables
            post_hashtags = Table(
                'post_hashtags', Base.metadata,
                Column('post_id', Integer, ForeignKey('posts.id', ondelete='CASCADE')),
                Column('hashtag_id', Integer, ForeignKey('hashtags.id', ondelete='CASCADE'))
            )

            post_mentions = Table(
                'post_mentions', Base.metadata,
                Column('post_id', Integer, ForeignKey('posts.id', ondelete='CASCADE')),
                Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'))
            )

            thread_collaborators = Table(
                'thread_collaborators', Base.metadata,
                Column('thread_id', Integer, ForeignKey('threads.id', ondelete='CASCADE')),
                Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'))
            )

            class Thread(Base):
                __tablename__ = 'threads'
                
                id = Column(Integer, primary_key=True, index=True)
                creator_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
                created_at = Column(DateTime, default=datetime.utcnow)
                is_collaborative = Column(Boolean, default=False)
                
                # Relationships
                creator = relationship("User", back_populates="created_threads")
                collaborators = relationship("User", secondary=thread_collaborators)
                posts = relationship("Post", back_populates="thread")

            class Post(Base):
                __tablename__ = 'posts'
                
                id = Column(Integer, primary_key=True, index=True)
                content = Column(String(500), nullable=False)
                author_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
                created_at = Column(DateTime, default=datetime.utcnow)
                
                # Thread fields
                thread_id = Column(Integer, ForeignKey('threads.id', ondelete='CASCADE'), nullable=True)
                position_in_thread = Column(Integer, nullable=True)
                
                # Reply fields
                reply_to_id = Column(Integer, ForeignKey('posts.id', ondelete='SET NULL'), nullable=True)
                
                # Vector field for semantic search
                content_vector = Column(ARRAY(Float), nullable=True)
                
                # Metrics
                like_count = Column(Integer, default=0)
                repost_count = Column(Integer, default=0)
                
                # Relationships
                author = relationship("User", back_populates="posts")
                thread = relationship("Thread", back_populates="posts")
                replies = relationship("Post", 
                                    backref=relationship("Post", remote_side=[id]),
                                    cascade="all, delete-orphan")
                hashtags = relationship("Hashtag", secondary=post_hashtags)
                mentioned_users = relationship("User", secondary=post_mentions)

            class Hashtag(Base):
                __tablename__ = 'hashtags'
                
                id = Column(Integer, primary_key=True, index=True)
                tag = Column(String, unique=True, index=True)
                created_at = Column(DateTime, default=datetime.utcnow)
                usage_count = Column(Integer, default=0)
                
                # Relationships
                posts = relationship("Post", secondary=post_hashtags)
        ''')

    def generate_schema(self) -> str:
        return textwrap.dedent('''
            from datetime import datetime
            from typing import Optional, List
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

            class ThreadBase(BaseModel):
                is_collaborative: bool = False

                class Config:
                    from_attributes = True

            class ThreadCreate(ThreadBase):
                posts: List[str]  # List of post contents for thread

            class ThreadUpdate(BaseModel):
                is_collaborative: Optional[bool] = None
        ''')

    def generate_router(self) -> str:
        return textwrap.dedent('''
            from fastapi import APIRouter, Depends, HTTPException, status
            from sqlalchemy.ext.asyncio import AsyncSession
            from typing import List
            from app.auth.dependencies import current_active_user
            from app.db.base import get_async_session
            from app.auth.models import User
            from . import service
            from .schemas import PostCreate, PostUpdate, ThreadCreate, ThreadUpdate

            router = APIRouter(prefix="/posts", tags=["posts"])

            @router.post("/", response_model=dict)
            async def create_post(
                post: PostCreate,
                user: User = Depends(current_active_user),
                session: AsyncSession = Depends(get_async_session)
            ):
                return await service.create_post(session, user.id, post)

            @router.post("/thread", response_model=dict)
            async def create_thread(
                thread: ThreadCreate,
                user: User = Depends(current_active_user),
                session: AsyncSession = Depends(get_async_session)
            ):
                return await service.create_thread(session, user.id, thread)

            @router.get("/{post_id}", response_model=dict)
            async def get_post(
                post_id: int,
                session: AsyncSession = Depends(get_async_session)
            ):
                post = await service.get_post(session, post_id)
                if not post:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Post not found"
                    )
                return post
        ''')

    def generate_service(self) -> str:
        return textwrap.dedent('''
            from sqlalchemy.ext.asyncio import AsyncSession
            from sqlalchemy import select
            from typing import List, Optional
            from .models import Post, Thread, Hashtag
            from .schemas import PostCreate, PostUpdate, ThreadCreate
            
            async def create_post(session: AsyncSession, user_id: int, post_data: PostCreate):
                post = Post(
                    author_id=user_id,
                    content=post_data.content,
                    thread_id=post_data.thread_id,
                    reply_to_id=post_data.reply_to_id
                )
                
                session.add(post)
                await session.commit()
                await session.refresh(post)
                return post

            async def create_thread(session: AsyncSession, user_id: int, thread_data: ThreadCreate):
                # Create thread
                thread = Thread(creator_id=user_id, is_collaborative=thread_data.is_collaborative)
                session.add(thread)
                await session.flush()
                
                # Create posts in thread
                for idx, content in enumerate(thread_data.posts, 1):
                    post = Post(
                        author_id=user_id,
                        content=content,
                        thread_id=thread.id,
                        position_in_thread=idx
                    )
                    session.add(post)
                
                await session.commit()
                await session.refresh(thread)
                return thread

            async def get_post(session: AsyncSession, post_id: int) -> Optional[Post]:
                result = await session.execute(
                    select(Post).where(Post.id == post_id)
                )
                return result.scalar_one_or_none()
        ''')

    def create_files(self):
        # Create module directory
        self.module_path.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py
        (self.module_path / "__init__.py").touch()
        
        # Create files
        files = {
            "models.py": self.generate_model,
            "schemas.py": self.generate_schema,
            "router.py": self.generate_router,
            "service.py": self.generate_service
        }
        
        for filename, generator in files.items():
            with open(self.module_path / filename, "w") as f:
                f.write(generator())

@app.command()
def generate(path: str = "app"):
    """Generate post module files"""
    generator = PostModuleGenerator(path)
    generator.create_files()
    typer.echo(f"Post module generated successfully in {path}/post/")

if __name__ == "__main__":
    app()