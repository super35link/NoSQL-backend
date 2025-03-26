"""
MongoDB implementation of hashtag router.
Replaces the SQL-dependent implementation with MongoDB.
"""
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, Query


from app.posts.schemas.classification_schemas import HashtagPostsResponse, HashtagResponse
from app.posts.services.nosql_core_post_service import NoSQLCorePostService
from app.auth.users import current_active_user
from app.db.models import User

router = APIRouter()

# Initialize the NoSQL post service
nosql_post_service = NoSQLCorePostService()


@router.get("/hashtags/trending", response_model=List[HashtagResponse])
async def get_trending_hashtags(
    limit: int = Query(10, ge=1, le=50),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get trending hashtags using MongoDB implementation.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Get trending hashtags from MongoDB
    cursor = nosql_post_service.db.hashtag_stats.find().sort("post_count", -1).limit(limit)
    
    trending_hashtags = []
    async for hashtag in cursor:
        trending_hashtags.append(HashtagResponse(
            tag=hashtag["tag"],
            post_count=hashtag["post_count"],
            follower_count=hashtag.get("follower_count", 0)
        ))
    
    return trending_hashtags

@router.get("/hashtags/{tag}", response_model=HashtagPostsResponse)
async def get_hashtag_posts(
    tag: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get posts with a specific hashtag using MongoDB implementation.
    """
    # Get posts with hashtag
    posts = await nosql_post_service.get_posts_by_hashtag(
        hashtag=tag,
        skip=skip,
        limit=limit
    )
    
    # Get total count
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    total_count = await nosql_post_service.posts_collection.count_documents(
        {"hashtags": tag, "is_deleted": False, "is_hidden": False}
    )
    
    # Format response
    return HashtagPostsResponse(
        tag=tag,
        posts=posts,
        total_count=total_count
    )

@router.post("/hashtags/follow/{tag}", response_model=Dict[str, bool])
async def follow_hashtag(
    tag: str,
    current_user: User = Depends(current_active_user)
):
    """
    Follow a hashtag using MongoDB implementation.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Add user to hashtag followers
    result = await nosql_post_service.db.hashtag_follows.update_one(
        {"tag": tag, "user_id": current_user.id},
        {"$set": {"followed_at": nosql_post_service.db.datetime.utcnow()}},
        upsert=True
    )
    
    # Update follower count
    await nosql_post_service.db.hashtag_stats.update_one(
        {"tag": tag},
        {"$inc": {"follower_count": 1}},
        upsert=True
    )
    
    return {"success": True}

@router.post("/hashtags/unfollow/{tag}", response_model=Dict[str, bool])
async def unfollow_hashtag(
    tag: str,
    current_user: User = Depends(current_active_user)
):
    """
    Unfollow a hashtag using MongoDB implementation.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Remove user from hashtag followers
    result = await nosql_post_service.db.hashtag_follows.delete_one(
        {"tag": tag, "user_id": current_user.id}
    )
    
    # Update follower count if user was following
    if result.deleted_count > 0:
        await nosql_post_service.db.hashtag_stats.update_one(
            {"tag": tag},
            {"$inc": {"follower_count": -1}}
        )
    
    return {"success": True}

@router.get("/hashtags/followed", response_model=List[HashtagResponse])
async def get_followed_hashtags(
    current_user: User = Depends(current_active_user)
):
    """
    Get hashtags followed by the current user using MongoDB implementation.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Get hashtags followed by user
    cursor = nosql_post_service.db.hashtag_follows.find({"user_id": current_user.id})
    
    followed_tags = []
    async for follow in cursor:
        tag = follow["tag"]
        
        # Get hashtag stats
        stats = await nosql_post_service.db.hashtag_stats.find_one({"tag": tag})
        
        if stats:
            followed_tags.append(HashtagResponse(
                tag=tag,
                post_count=stats.get("post_count", 0),
                follower_count=stats.get("follower_count", 0)
            ))
        else:
            followed_tags.append(HashtagResponse(
                tag=tag,
                post_count=0,
                follower_count=0
            ))
    
    return followed_tags
