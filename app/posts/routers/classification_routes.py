"""
MongoDB implementation of classification router.
Replaces the SQL-dependent implementation with MongoDB.
"""
from typing import List, Optional, Dict, Any, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from app.posts.services.nosql_core_post_service import NoSQLCorePostService
from app.auth.users import current_active_user
from app.db.models import User

router = APIRouter()

# Initialize the NoSQL post service
nosql_post_service = NoSQLCorePostService()

class TopicItem(BaseModel):
    """Schema for a topic classification item."""
    topic: str
    confidence: float

class SentimentScores(BaseModel):
    """Schema for sentiment analysis scores."""
    positive: float
    negative: float
    neutral: float

class ClassificationRequest(BaseModel):
    """Schema for classification request."""
    topics: List[Dict[str, Union[str, float]]]
    sentiment: Optional[Dict[str, float]] = None

class ClassificationResponse(BaseModel):
    """Schema for classification response."""
    post_id: str
    topics: List[TopicItem]
    sentiment: Optional[SentimentScores] = None
    created_at: str
    updated_at: Optional[str] = None

@router.post("/posts/{post_id}/classify", response_model=ClassificationResponse)
async def classify_post(
    post_id: str,
    classification: ClassificationRequest,
    current_user: User = Depends(current_active_user)
):
    """
    Add content classification to a post using MongoDB.
    """
    # Get the post to check ownership or admin status
    post = await nosql_post_service.get_post(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Check if user is the author or has admin privileges
    # This is a simplified check - you might want to add proper role-based checks
    if post["author_id"] != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to classify this post"
        )
    
    # Add classification
    success = await nosql_post_service.add_post_classification(
        post_id=post_id,
        topics=classification.topics,
        sentiment=classification.sentiment
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add classification"
        )
    
    # Get the updated classification
    classification_data = await nosql_post_service.get_post_classification(post_id)
    
    if not classification_data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve classification"
        )
    
    # Format response
    topics = [
        TopicItem(topic=item["topic"], confidence=item["confidence"])
        for item in classification_data["topics"]
    ]
    
    sentiment = None
    if classification_data.get("sentiment"):
        sentiment = SentimentScores(
            positive=classification_data["sentiment"].get("positive", 0.0),
            negative=classification_data["sentiment"].get("negative", 0.0),
            neutral=classification_data["sentiment"].get("neutral", 0.0)
        )
    
    return ClassificationResponse(
        post_id=post_id,
        topics=topics,
        sentiment=sentiment,
        created_at=classification_data["created_at"].isoformat(),
        updated_at=classification_data.get("updated_at").isoformat() if classification_data.get("updated_at") else None
    )

@router.get("/posts/{post_id}/classification", response_model=ClassificationResponse)
async def get_post_classification(
    post_id: str,
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get content classification for a post using MongoDB.
    """
    # Get the post to check if it exists
    post = await nosql_post_service.get_post(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Get classification
    classification_data = await nosql_post_service.get_post_classification(post_id)
    
    if not classification_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classification not found for this post"
        )
    
    # Format response
    topics = [
        TopicItem(topic=item["topic"], confidence=item["confidence"])
        for item in classification_data["topics"]
    ]
    
    sentiment = None
    if classification_data.get("sentiment"):
        sentiment = SentimentScores(
            positive=classification_data["sentiment"].get("positive", 0.0),
            negative=classification_data["sentiment"].get("negative", 0.0),
            neutral=classification_data["sentiment"].get("neutral", 0.0)
        )
    
    return ClassificationResponse(
        post_id=post_id,
        topics=topics,
        sentiment=sentiment,
        created_at=classification_data["created_at"].isoformat(),
        updated_at=classification_data.get("updated_at").isoformat() if classification_data.get("updated_at") else None
    )

@router.get("/topics/{topic}/posts", response_model=List[Dict[str, Any]])
async def get_posts_by_topic(
    topic: str,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(current_active_user)
):
    """
    Get posts classified with a specific topic using MongoDB.
    """
    # Ensure MongoDB connection is initialized
    if not nosql_post_service.db:
        await nosql_post_service.initialize()
    
    # Find post IDs with this topic and minimum confidence
    cursor = nosql_post_service.db.post_classifications.find({
        "topics": {
            "$elemMatch": {
                "topic": topic,
                "confidence": {"$gte": min_confidence}
            }
        }
    })
    
    post_ids = []
    async for doc in cursor:
        post_ids.append(doc["post_id"])
    
    # Get posts by IDs
    posts = []
    for post_id in post_ids[skip:skip+limit]:
        post = await nosql_post_service.get_post(str(post_id))
        if post and not post["is_deleted"] and not post["is_hidden"]:
            posts.append(post)
    
    return posts
