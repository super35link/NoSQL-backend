from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import get_async_session
from app.posts.services.content_classification_service import ContentClassificationService

router = APIRouter(prefix="/content", tags=["content"])
service = ContentClassificationService()

@router.get("/trending/hashtags")
async def get_trending_hashtags(
    timeframe: str = Query(default="24h", enum=["1h", "24h", "7d", "30d"]),
    limit: int = Query(default=10, le=50)
):
    return await service.get_trending_hashtags(timeframe, limit)

@router.get("/hashtags/{hashtag}/posts")
async def get_posts_by_hashtag(
    hashtag: str,
    session: AsyncSession = Depends(get_async_session),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100)
):
    return await service.get_posts_by_hashtag(session, hashtag, skip, limit)

@router.get("/topics/{topic}/distribution")
async def get_topic_distribution(
    topic: str,
    session: AsyncSession = Depends(get_async_session)
):
    return await service.get_topic_distribution(session, topic)