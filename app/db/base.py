from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

class Base(DeclarativeBase):
    pass

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True  # Set to False in production
)

# Create session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_maker()
    try:
        yield session
    finally:
        await session.close()