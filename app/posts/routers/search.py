from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from app.db.base import get_async_session
from app.posts.services.comprehensive_search_service import SearchService
from app.posts.schemas.search_schemas import SearchFilters, SearchResult

router = APIRouter(prefix="/search", tags=["search"])
search_service = SearchService()

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
    hashtags: Optional[str] = None,  # Comma-separated hashtags
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session)
):
    """Search posts with various filters"""
    filters = SearchFilters(
        author_id=author_id,
        hashtags=hashtags.split(',') if hashtags else None,
        date_from=date_from,
        date_to=date_to,
        min_likes=min_likes
    )
    
    return await search_service.search_posts(
        session=session,
        query=query,
        search_type=search_type,
        filters=filters,
        limit=limit,
        offset=offset
    )

@router.get("/suggest")
async def suggest_search_terms(
    partial_query: str,
    limit: int = Query(default=5, le=20),
    session: AsyncSession = Depends(get_async_session)
):
    """Get search suggestions based on partial input"""
    return await search_service.suggest_search_terms(
        session=session,
        partial_query=partial_query,
        limit=limit
    )