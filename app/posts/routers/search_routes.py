"""
MongoDB implementation of search router.
Replaces the SQL-dependent implementation with MongoDB.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from app.posts.services.nosql_core_post_service import NoSQLCorePostService
from app.auth.users import current_active_user
from app.db.models import User

router = APIRouter()

# Initialize the NoSQL post service
nosql_post_service = NoSQLCorePostService()

class SearchResponse(BaseModel):
    """Schema for search response."""
    query: str
    posts: List[Dict[str, Any]]
    total_count: int
    execution_time_ms: float

@router.get("/search", response_model=SearchResponse)
async def search_posts(
    q: str = Query(..., min_length=1, description="Search query"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Search posts using MongoDB text search.
    """
    import time
    start_time = time.time()
    
    # Perform search
    posts = await nosql_post_service.search_posts(
        query=q,
        skip=skip,
        limit=limit
    )
    
    # Get total count
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    total_count = await nosql_post_service.posts_collection.count_documents(
        {"$text": {"$search": q}, "is_deleted": False, "is_hidden": False}
    )
    
    # Calculate execution time
    execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    
    # Format response
    return SearchResponse(
        query=q,
        posts=posts,
        total_count=total_count,
        execution_time_ms=execution_time
    )

@router.get("/search/advanced", response_model=SearchResponse)
async def advanced_search(
    content: Optional[str] = None,
    author_id: Optional[int] = None,
    hashtag: Optional[str] = None,
    before_date: Optional[str] = None,
    after_date: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Advanced search with multiple criteria using MongoDB.
    """
    import time
    from datetime import datetime
    
    start_time = time.time()
    
    # Build query filter
    query_filter = {"is_deleted": False, "is_hidden": False}
    
    if content:
        query_filter["$text"] = {"$search": content}
    
    if author_id:
        query_filter["author_id"] = author_id
    
    if hashtag:
        query_filter["hashtags"] = hashtag
    
    # Date filters
    date_filter = {}
    if before_date:
        try:
            before_datetime = datetime.fromisoformat(before_date)
            date_filter["$lte"] = before_datetime
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid before_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
            )
    
    if after_date:
        try:
            after_datetime = datetime.fromisoformat(after_date)
            date_filter["$gte"] = after_datetime
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid after_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
            )
    
    if date_filter:
        query_filter["created_at"] = date_filter
    
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Execute query
    cursor = nosql_post_service.posts_collection.find(query_filter)
    
    # Apply sorting
    if content:
        # If text search is used, sort by text score
        cursor = cursor.sort([("score", {"$meta": "textScore"})])
    else:
        # Otherwise sort by creation date
        cursor = cursor.sort("created_at", -1)
    
    # Apply pagination
    cursor = cursor.skip(skip).limit(limit)
    
    # Get results
    posts = []
    async for post in cursor:
        # Convert ObjectId to string for JSON serialization
        post["_id"] = str(post["_id"])
        if post.get("reply_to_id"):
            post["reply_to_id"] = str(post["reply_to_id"])
        posts.append(post)
    
    # Get total count
    total_count = await nosql_post_service.posts_collection.count_documents(query_filter)
    
    # Calculate execution time
    execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    
    # Format response
    return SearchResponse(
        query=content or "Advanced search",
        posts=posts,
        total_count=total_count,
        execution_time_ms=execution_time
    )
