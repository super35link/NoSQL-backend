"""
MongoDB implementation of threads router.
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

class ThreadResponse(BaseModel):
    """Schema for thread response."""
    root_post: Dict[str, Any]
    replies: List[Dict[str, Any]]
    total_replies: int
    depth: int

@router.get("/posts/{post_id}/thread", response_model=ThreadResponse)
async def get_post_thread(
    post_id: str,
    depth: int = Query(2, ge=1, le=5),
    replies_limit: int = Query(10, ge=1, le=50),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get a post thread (root post and replies) using MongoDB.
    """
    # Get the post
    post = await nosql_post_service.get_post(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Find root post if this is a reply
    root_post = post
    current_depth = 0
    
    while root_post.get("reply_to_id") and current_depth < depth:
        parent_post = await nosql_post_service.get_post(root_post["reply_to_id"])
        if not parent_post:
            break
        
        root_post = parent_post
        current_depth += 1
    
    # Get replies to the root post
    replies = await nosql_post_service.get_post_replies(
        post_id=str(root_post["_id"]),
        limit=replies_limit
    )
    
    # Get total replies count
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    try:
        root_id_obj = nosql_post_service.db.ObjectId(root_post["_id"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )
    
    total_replies = await nosql_post_service.posts_collection.count_documents({
        "reply_to_id": root_id_obj,
        "is_deleted": False,
        "is_hidden": False
    })
    
    # Format response
    return ThreadResponse(
        root_post=root_post,
        replies=replies,
        total_replies=total_replies,
        depth=current_depth
    )

@router.get("/posts/{post_id}/conversation", response_model=List[Dict[str, Any]])
async def get_post_conversation(
    post_id: str,
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get the full conversation chain for a post using MongoDB.
    Returns the post and all its ancestors in chronological order.
    """
    # Get the post
    post = await nosql_post_service.get_post(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Build conversation chain
    conversation = [post]
    current_post = post
    
    # Traverse up the reply chain
    while current_post.get("reply_to_id"):
        parent_post = await nosql_post_service.get_post(current_post["reply_to_id"])
        if not parent_post:
            break
        
        conversation.insert(0, parent_post)  # Insert at beginning for chronological order
        current_post = parent_post
    
    return conversation

@router.get("/users/{user_id}/threads", response_model=List[ThreadResponse])
async def get_user_threads(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get threads started by a user using MongoDB.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Find root posts by user (posts that are not replies)
    cursor = nosql_post_service.posts_collection.find({
        "author_id": user_id,
        "reply_to_id": None,
        "is_deleted": False,
        "is_hidden": False
    }).sort("created_at", -1).skip(skip).limit(limit)
    
    # Build thread responses
    threads = []
    async for root_post in cursor:
        # Convert ObjectId to string
        root_post["_id"] = str(root_post["_id"])
        
        # Get replies
        replies = await nosql_post_service.get_post_replies(
            post_id=root_post["_id"],
            limit=5  # Limit to 5 replies per thread in this view
        )
        
        # Get total replies count
        try:
            root_id_obj = nosql_post_service.db.ObjectId(root_post["_id"])
        except Exception:
            continue
        
        total_replies = await nosql_post_service.posts_collection.count_documents({
            "reply_to_id": root_id_obj,
            "is_deleted": False,
            "is_hidden": False
        })
        
        # Add thread to response
        threads.append(ThreadResponse(
            root_post=root_post,
            replies=replies,
            total_replies=total_replies,
            depth=0
        ))
    
    return threads
