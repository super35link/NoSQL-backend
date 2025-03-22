import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime
from app.db.base import get_async_session
from app.posts.services.comprehensive_search_service import SearchService
from app.posts.schemas.search_schemas import SearchFilters, SearchResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/posts", response_model=dict)
async def search_posts(
    query: str,
    search_type: str = Query(
        default="combined",
        enum=["semantic", "text", "combined"]
    ),
    author_id: Optional[int] = None,
    min_likes: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    hashtags: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session)
):
    """Search posts with various filters"""
    search_service = SearchService()
    
    filters = SearchFilters(
        author_id=author_id,
        hashtags=hashtags.split(',') if hashtags else None,
        date_from=date_from,
        date_to=date_to,
        min_likes=min_likes
    )

    # Single transaction context    async with session.begin():
    result = await search_service.search_posts(
            session=session,
            query=query,
            search_type=search_type,
            filters=filters,
            limit=limit,
            offset=offset
        )
        
    return result

@router.get("/suggest")
async def suggest_search_terms(
    partial_query: str,
    limit: int = Query(default=5, le=20),
    session: AsyncSession = Depends(get_async_session)
):
    """Get search suggestions based on partial input"""
    search_service = SearchService()  # Create instance here
    return await search_service.suggest_search_terms(
        session=session,
        partial_query=partial_query,
        limit=limit
    )