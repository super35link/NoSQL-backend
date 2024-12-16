# tests/test_engagement.py
import asyncio
from datetime import datetime
from app.posts.services.engagement_service import PostEngagementService, InteractionType

async def test_engagement_service():
    service = PostEngagementService()
    
    # Test data
    post_id = 1
    user_1 = 101
    user_2 = 102

    # 1. Test like functionality
    print("\nTesting likes:")
    liked = await service.toggle_like(post_id, user_1)
    print(f"User {user_1} liked post: {liked}")
    
    stats = await service.get_engagement_stats(post_id)
    print(f"Engagement stats after like: {stats}")
    
    # 2. Test view functionality
    print("\nTesting views:")
    await service.increment_views(post_id, user_1)
    await service.increment_views(post_id, user_2)
    # Same user viewing again
    await service.increment_views(post_id, user_1)
    
    stats = await service.get_engagement_stats(post_id)
    print(f"Engagement stats after views: {stats}")
    
    # 3. Test user engagement status
    print("\nTesting user engagement:")
    user_engagement = await service.get_user_engagement(user_1, post_id)
    print(f"User {user_1} engagement: {user_engagement}")
    
    # 4. Test unlike
    print("\nTesting unlike:")
    unliked = await service.toggle_like(post_id, user_1)
    print(f"User {user_1} unliked post: {not unliked}")
    
    stats = await service.get_engagement_stats(post_id)
    print(f"Final engagement stats: {stats}")

if __name__ == "__main__":
    asyncio.run(test_engagement_service())